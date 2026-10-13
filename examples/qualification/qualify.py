"""Measure worker reasoning tiers on fixed, independently checked tasks.

A scripted Chief (no model calls) plans one task per family and spawns it on
the tier under test. Each tier and trial runs in its own project, so workers
cannot read each other's outputs. A check the workers never see verifies each
result; the event log gives turns, rejected actions, time and provider-reported
cost. Pass the written records to Project(qualifications=...) to route tasks.

    uv run python examples/qualification/qualify.py --trials 1
"""

import argparse
import asyncio
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from asyncio.subprocess import DEVNULL, PIPE
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from pydantic import Field, JsonValue, TypeAdapter, ValidationError

from guacamole import (
    AgentSpec,
    AgentTurn,
    Budget,
    Candidate,
    ContextPacket,
    ContextSpec,
    DecisionRequest,
    DeliverableSpec,
    Model,
    ProducedFile,
    Project,
    ProjectRequest,
    Qualification,
    Requirement,
    TaskAuthorization,
    ToolGrant,
    ToolRegistry,
    Usage,
    WorkPlan,
)
from guacamole.context import ProviderError
from guacamole.contracts import AgentState, Decide, Rationale, Record, Spawn, Wait
from guacamole.providers.claude import ClaudeReasoning

ROOT = Path(__file__).resolve().parent
BRIEF = "Qualify worker reasoning tiers on fixed, independently checked tasks."
TASK_BUDGET = Budget(max_steps=20, max_tool_calls=15, max_seconds=1500)


def tiers() -> dict[str, ClaudeReasoning]:
    """Profiles under test; context windows as the Claude CLI reports them."""
    options = {"web_search": False, "timeout_s": 900}
    return {
        "haiku-low": ClaudeReasoning(
            model="claude-haiku-5-5",
            effort="low",
            context_capacity_tokens=1_000_000,
            **options,
        ),
        "sonnet-medium": ClaudeReasoning(
            model="claude-sonnet-5-5",
            effort="medium",
            context_capacity_tokens=1_000_000,
            **options,
        ),
        "opus-high": ClaudeReasoning(effort="high", **options),
    }


class MotorExtract(Model):
    kv_rpm_per_v: float
    max_continuous_current_a: float
    mass_with_leads_kg: float
    full_throttle_thrust_n: float
    full_throttle_efficiency_g_per_w: float


class HopApogee(Model):
    apogee_m: float
    apogee_time_s: float


class Trial(Model):
    family: str
    tier: str
    number: int
    provider: str
    model: str
    effort: str | None
    failure: str | None  # None: completed and passed its hidden check
    cost_usd: float | None
    seconds: float
    turns: int
    rejected_actions: int


class PythonRun(Model):
    returncode: int
    stdout: str
    stderr: str


type Seconds = Annotated[float, Field(gt=0, le=300)]


def register_tools(project: Project) -> tuple[ToolGrant, ...]:
    async def read_text(path: str) -> str:
        """Read up to 20000 UTF-8 characters of a sandbox-relative file."""
        return project.output_path(Path(path)).read_text(encoding="utf-8")[:20_000]

    async def write_text(path: str, text: str) -> ProducedFile:
        """Write a UTF-8 file at a sandbox-relative path."""
        destination = project.output_path(Path(path))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
        return ProducedFile.from_path(destination)

    async def run_python(script: str, timeout_s: Seconds = 60.0) -> PythonRun:
        """Run a sandbox-relative script with the sandbox as working directory."""
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(project.output_path(Path(script))),
            cwd=project.sandbox,
            env={"PATH": os.environ["PATH"], "HOME": str(project.sandbox)},
            stdin=DEVNULL,
            stdout=PIPE,
            stderr=PIPE,
        )
        try:
            out, err = await asyncio.wait_for(process.communicate(), timeout_s)
        except TimeoutError:
            process.kill()
            await process.wait()
            return PythonRun(returncode=-1, stdout="", stderr="Timed out")
        return PythonRun(
            returncode=process.returncode or 0,
            stdout=out.decode(errors="replace")[-8000:],
            stderr=err.decode(errors="replace")[-8000:],
        )

    return tuple(
        project.tools.register(f).definition.grant
        for f in (read_text, write_text, run_python)
    )


def check_extraction(_: Path, result: JsonValue) -> str | None:
    got = MotorExtract.model_validate(result).model_dump()
    expected = {
        "kv_rpm_per_v": 580,
        "max_continuous_current_a": 26,
        "mass_with_leads_kg": 0.089,
        "full_throttle_thrust_n": 3020 * 9.80665e-3,
        "full_throttle_efficiency_g_per_w": 3020 / 575,
    }
    wrong = {
        k: (got[k], round(v, 4))
        for k, v in expected.items()
        if not math.isclose(got[k], v, rel_tol=0.01)
    }
    return f"Wrong values (got, expected): {wrong}" if wrong else None


def hop_reference() -> tuple[float, float]:
    """RK4 at 0.1 ms; apogee interpolated where velocity crosses zero."""
    mass, g, thrust, burn, drag = 3.0, 9.80665, 45.0, 2.5, 0.5 * 1.225 * 0.012

    def acceleration(t: float, v: float) -> float:
        return ((thrust if t < burn else 0.0) - drag * v * abs(v)) / mass - g

    t, h, v, dt = 0.0, 0.0, 0.0, 1e-4
    while True:
        k1v, k1h = acceleration(t, v), v
        k2v = acceleration(t + dt / 2, v + dt / 2 * k1v)
        k2h = v + dt / 2 * k1v
        k3v = acceleration(t + dt / 2, v + dt / 2 * k2v)
        k3h = v + dt / 2 * k2v
        k4v, k4h = acceleration(t + dt, v + dt * k3v), v + dt * k3v
        v1 = v + dt / 6 * (k1v + 2 * k2v + 2 * k3v + k4v)
        h1 = h + dt / 6 * (k1h + 2 * k2h + 2 * k3h + k4h)
        if t > burn and v1 <= 0:
            share = v / (v - v1)
            return h + share * (h1 - h), t + share * dt
        t, h, v = t + dt, h1, v1


def check_simulation(_: Path, result: JsonValue) -> str | None:
    got = HopApogee.model_validate(result)
    apogee, time = hop_reference()
    if math.isclose(got.apogee_m, apogee, rel_tol=0.005) and math.isclose(
        got.apogee_time_s, time, rel_tol=0.005
    ):
        return None
    return (
        f"Apogee {got.apogee_m} m at {got.apogee_time_s} s; "
        f"expected {apogee:.3f} m at {time:.3f} s"
    )


def hidden_check(code: str, module: Path) -> str | None:
    """Run code with the produced module's path; a nonzero exit is a failure."""
    if not module.is_file():
        return f"Missing {module.name}"
    with tempfile.TemporaryDirectory() as directory:
        script = Path(directory) / "check.py"
        script.write_text(code, encoding="utf-8")
        try:
            run = subprocess.run(
                [sys.executable, "-I", str(script), str(module.resolve())],
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return "Hidden check timed out"
    return None if run.returncode == 0 else run.stderr.strip()[-600:]


LOAD = """import importlib.util, math, sys
spec = importlib.util.spec_from_file_location("candidate", sys.argv[1])
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)
"""

PID_CHECK = (
    LOAD
    + """
class Reference:
    def __init__(self, kp, ki, kd, dt, out_min, out_max):
        self.kp, self.ki, self.kd, self.dt = kp, ki, kd, dt
        self.out_min, self.out_max = out_min, out_max
        self.reset()

    def reset(self):
        self.integral, self.previous = 0.0, None

    def update(self, setpoint, measurement):
        e = setpoint - measurement
        d = 0.0 if self.previous is None else -(measurement - self.previous) / self.dt
        self.previous = measurement
        candidate = self.integral + self.ki * e * self.dt
        u = self.kp * e + candidate + self.kd * d
        if not ((u > self.out_max and e > 0) or (u < self.out_min and e < 0)):
            self.integral = candidate
        u = self.kp * e + self.integral + self.kd * d
        return min(max(u, self.out_min), self.out_max)


def run(cls, gains, setpoints, reset_at):
    controller, measurement, out = cls(**gains), 0.0, []
    for k, setpoint in enumerate(setpoints):
        if k == reset_at:
            controller.reset()
        u = controller.update(setpoint, measurement)
        out.append(u)
        measurement += gains["dt"] * 2.0 * (u - measurement)  # First-order plant
    return out


cases = (
    (dict(kp=1.2, ki=0.5, kd=0.05, dt=0.02, out_min=-1.0, out_max=1.0), [0.8] * 200, None),
    (dict(kp=0.4, ki=3.0, kd=0.0, dt=0.05, out_min=-1.0, out_max=1.0), [-5.0] * 60 + [0.5] * 140, None),
    (dict(kp=2.0, ki=1.0, kd=0.3, dt=0.01, out_min=-0.5, out_max=2.0), [1.0] * 50 + [-1.0] * 50, 70),
)
for n, (gains, setpoints, reset_at) in enumerate(cases):
    got = run(candidate.PID, gains, setpoints, reset_at)
    want = run(Reference, gains, setpoints, reset_at)
    for k, (a, b) in enumerate(zip(got, want, strict=True)):
        if not math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9):
            sys.exit(f"Case {n}, step {k}: returned {a!r}, expected {b!r}")
"""
)

DIAGNOSIS_CHECK = (
    LOAD
    + """
def smooth(values, window=5):
    half = window // 2
    chunks = [values[max(0, i - half) : i + half + 1] for i in range(len(values))]
    return [sum(c) / len(c) for c in chunks]


def apogee(rows, window=5):
    altitudes = smooth([a for _, a in rows], window)
    k = max(range(len(altitudes)), key=altitudes.__getitem__)
    return rows[k][0], altitudes[k]


def same(got, want, label):
    if len(got) != len(want) or not all(math.isclose(a, b, abs_tol=1e-9) for a, b in zip(got, want)):
        sys.exit(f"{label}: returned {got!r}, expected {want!r}")


series = [3.0, 1.0, 4.0, 1.0, 5.0, 9.0, 2.0, 6.0]
for window in (3, 5, 7):
    same(candidate.smooth(series, window), smooth(series, window), f"smooth window {window}")
for values in ([2.0], [1.0, 4.0]):
    same(candidate.smooth(values), smooth(values), f"smooth {values}")
rows = [(0.05 * i, 40 * math.sin(0.045 * i) + 0.3 * math.sin(7 * i)) for i in range(80)]
same(candidate.apogee(rows), apogee(rows), "apogee")
"""
)

FAMILIES: dict[str, tuple[str, str, Callable[[Path, JsonValue], str | None]]] = {
    "extraction": (
        (
            "Read inputs/motor_datasheet.txt. For the 580 KV variant, finish with a "
            "MotorExtract@1 result: kv_rpm_per_v; max_continuous_current_a; "
            "mass_with_leads_kg (kilograms, including leads); full_throttle_thrust_n "
            "(100% throttle bench thrust in newtons, using 9.80665 m/s^2); and "
            "full_throttle_efficiency_g_per_w (that thrust in grams-force divided by "
            "the electrical power at 100% throttle)."
        ),
        "MotorExtract@1",
        check_extraction,
    ),
    "simulation": (
        (
            "Compute the apogee of a 1-D vertical hop and finish with a HopApogee@1 "
            "result (apogee_m, apogee_time_s), each within 0.5%. Mass 3.0 kg, constant. "
            "Thrust 45.0 N upward from t = 0 until t = 2.5 s, then zero. Gravity "
            "9.80665 m/s^2. Drag opposes velocity with magnitude 0.5*rho*CdA*v^2, "
            "rho = 1.225 kg/m^3, CdA = 0.012 m^2. Starts at rest at altitude 0. Write "
            "the integration under answers/simulation/ and run it with run_python; "
            "do not estimate by hand."
        ),
        "HopApogee@1",
        check_simulation,
    ),
    "implementation": (
        (
            "Write answers/implementation/pid.py defining class PID(kp, ki, kd, dt, "
            "out_min, out_max) with methods update(setpoint, measurement) -> float and "
            "reset(). The integral starts at 0. Each update: (1) e = setpoint - "
            "measurement. (2) d = -(measurement - previous measurement) / dt, and d = 0 "
            "on the first update and the first update after reset(). (3) candidate = "
            "integral + ki*e*dt and u = kp*e + candidate + kd*d. (4) Anti-windup: keep "
            "the previous integral when u > out_max and e > 0, or when u < out_min and "
            "e < 0; otherwise integral = candidate. (5) Return kp*e + integral + kd*d "
            "using the integral from step 4, clamped to [out_min, out_max]. reset() "
            "sets the integral to 0 and forgets the previous measurement. Test it with "
            "run_python, then finish with a TaskReport@1."
        ),
        "TaskReport@1",
        lambda sandbox, _: hidden_check(
            PID_CHECK, sandbox / "answers/implementation/pid.py"
        ),
    ),
    "diagnosis": (
        (
            "inputs/flight_log_tools.py fails inputs/test_flight_log_tools.py; run that "
            "test with run_python to see the failure. Find the root cause and write a "
            "corrected copy of the whole module to answers/diagnosis/flight_log_tools.py, "
            "fixing the cause rather than the symptom and keeping each function's "
            "documented behaviour. Leave inputs/ unchanged. Finish with a TaskReport@1 "
            "naming the root cause."
        ),
        "TaskReport@1",
        lambda sandbox, _: hidden_check(
            DIAGNOSIS_CHECK, sandbox / "answers/diagnosis/flight_log_tools.py"
        ),
    ),
}


class ScriptedChief:
    """Records the brief, plans the fixed tasks and spawns them; no model calls."""

    name, model, context_capacity_tokens = "scripted-chief", "none", 10_000_000

    def __init__(self, tasks: tuple[TaskAuthorization, ...]) -> None:
        self.tasks, self.turns = tasks, 0

    async def count_tokens(self, prompt: str) -> int:
        return len(prompt.encode())

    async def respond(self, packet: ContextPacket) -> AgentTurn:
        data = json.loads(packet.prompt)
        observation = data["state"]["last_observation"]
        if "error_type" in observation:
            raise ProviderError(f"Scripted plan rejected: {observation['detail']}")
        turn, self.turns = self.turns, self.turns + 1
        refs = {r.kind: r for r in packet.sources}
        if turn == 0:
            action = Record(
                record=Requirement(
                    id="qualification",
                    wording=BRIEF,
                    source=refs["source"],
                    source_quote=BRIEF,
                )
            )
        elif turn == 1:
            requirement = refs["requirement"]
            plan = WorkPlan(
                stage="PDR",
                inputs=(requirement,),
                tasks=self.tasks,
                deliverables=(
                    DeliverableSpec(
                        id="qualification",
                        title="Qualification records",
                        stage="PDR",
                        requirements=(requirement,),
                        artifact_kinds=("qualification-record",),
                        acceptance_criteria=("Each task passes its hidden check",),
                    ),
                ),
            )
            action = Decide(
                selected="fixed-tasks",
                request=DecisionRequest(
                    question="Which tasks qualify the tier under test?",
                    kind="work_plan",
                    criteria=("One independently checked task per family",),
                    candidates=(
                        Candidate(id="fixed-tasks", description=BRIEF, plan=plan),
                    ),
                ),
            )
        elif turn - 2 < len(self.tasks):
            action = Spawn(
                decision_id=data["agent"]["decision_id"],
                task_id=self.tasks[turn - 2].id,
            )
        else:
            action = Wait(reason="Workers run their tasks")
        return AgentTurn(
            rationale=Rationale(objective=BRIEF, explanation="Scripted qualification"),
            action=action,
        )


async def trial(tier: str, number: int, directory: Path) -> list[Trial]:
    provider = tiers()[tier]
    registry = ToolRegistry()
    registry.schema("MotorExtract@1", MotorExtract)
    registry.schema("HopApogee@1", HopApogee)
    with Project(
        directory / "workspace",
        sandbox=directory / "sandbox",
        tools=registry,
        tiers={tier: provider},
        max_concurrent_calls=2,
    ) as project:
        shutil.copytree(ROOT / "inputs", project.sandbox / "inputs")
        grants = register_tools(project)
        project.reasoning = ScriptedChief(
            tuple(
                TaskAuthorization(
                    id=family,
                    objective=objective,
                    tools=grants,
                    result_schema=schema,
                    budget=TASK_BUDGET,
                    family=family,
                    tier=tier,
                )
                for family, (objective, schema, _) in FAMILIES.items()
            )
        )
        await project.run(
            ProjectRequest(
                description=BRIEF,
                context=ContextSpec(
                    instructions="read_text, write_text and run_python take "
                    "sandbox-relative paths. Python has only its standard library.",
                    max_input_tokens=400_000,
                    reserved_output_tokens=16_000,
                ),
                budget=Budget(max_seconds=3600, max_agents=len(FAMILIES)),
            )
        )
        await project.drain()
        store, events = project.store, project.events()
        trials = []
        agents = [
            store.model("agent", s.ref.id, AgentSpec) for s in store.list("agent")
        ]
        for agent in agents:
            if agent.parent_id is None:
                continue
            state = store.model("agent_state", agent.id, AgentState)
            request = project.activity.get(state.request_id)
            usage = sum(
                (
                    store.model("agent_turn", e.entity_id, AgentTurn).usage or Usage()
                    for e in events
                    if e.type == "provider.responded" and e.actor == agent.id
                ),
                Usage(),
            )
            try:
                verdict = FAMILIES[agent.task_id][2](project.sandbox, request.result)
            except ValidationError:
                verdict = "No result"
            # An unfinished task fails even with a correct artifact; say which it was.
            failure = (
                verdict
                if request.status == "completed"
                else f"Ended {state.status}, artifact "
                + ("correct" if verdict is None else "wrong")
                + f": {str(state.observation)[:600]}"
            )
            trials.append(
                Trial(
                    family=agent.task_id,
                    tier=tier,
                    number=number,
                    provider=provider.name,
                    model=provider.model,
                    effort=provider.effort,
                    failure=failure,
                    cost_usd=usage.cost_usd,
                    seconds=state.elapsed_s,
                    turns=sum(
                        e.type == "provider.dispatched" and e.actor == agent.id
                        for e in events
                    ),
                    rejected_actions=sum(
                        e.type == "action.rejected" and e.entity_id == agent.id
                        for e in events
                    ),
                )
            )
        if not trials:
            chief = next(a for a in agents if a.parent_id is None)
            state = store.model("agent_state", chief.id, AgentState)
            raise RuntimeError(f"No workers ran: {state.observation}")
        return trials


def records(trials: list[Trial]) -> list[Qualification]:
    grouped: dict[tuple[str, str, str, str | None], list[Trial]] = {}
    for t in trials:
        grouped.setdefault((t.family, t.provider, t.model, t.effort), []).append(t)
    return [
        Qualification(
            family=family,
            provider=provider,
            model=model,
            effort=effort,
            trials=len(group),
            passed=sum(t.failure is None for t in group),
            cost_usd=None
            if any(t.cost_usd is None for t in group)
            else sum(t.cost_usd or 0.0 for t in group),
            seconds=sum(t.seconds for t in group),
            turns=sum(t.turns for t in group),
            rejected_actions=sum(t.rejected_actions for t in group),
        )
        for (family, provider, model, effort), group in grouped.items()
    ]


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--tiers", default=",".join(tiers()))
    parser.add_argument("--out", type=Path, default=ROOT / "qualifications.json")
    args = parser.parse_args()
    if shutil.which("claude") is None:
        raise SystemExit("Install the Claude Code CLI and run 'claude login'.")
    root = Path(tempfile.mkdtemp(prefix="guacamole-qualify-"))
    print(f"Workspaces: {root}", flush=True)
    runs = [
        (tier, n) for tier in args.tiers.split(",") for n in range(1, args.trials + 1)
    ]
    results = await asyncio.gather(
        *(trial(tier, n, root / f"{tier}-{n}") for tier, n in runs),
        return_exceptions=True,
    )
    trials: list[Trial] = []
    for (tier, n), result in zip(runs, results, strict=True):
        if isinstance(result, BaseException):
            print(f"{tier} trial {n} failed to run: {result!r}")
        else:
            trials.extend(result)
    (root / "trials.json").write_bytes(
        TypeAdapter(list[Trial]).dump_json(trials, indent=2)
    )
    for t in sorted(trials, key=lambda t: (t.family, t.tier, t.number)):
        cost = f"${t.cost_usd:.3f}" if t.cost_usd is not None else "$?"
        print(
            f"{t.family:<15}{t.tier:<15}{'FAIL' if t.failure else 'pass':<6}"
            f"{cost:>8}{t.seconds:>7.0f} s{t.turns:>4} turns"
            f"{t.rejected_actions:>3} rejected"
            + (f"\n    {t.failure}" if t.failure else "")
        )
    measured = records(trials)
    args.out.write_bytes(
        TypeAdapter(list[Qualification]).dump_json(measured, indent=2) + b"\n"
    )
    print(f"Wrote {len(measured)} records to {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
