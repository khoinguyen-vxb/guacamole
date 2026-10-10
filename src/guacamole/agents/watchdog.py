"""Runtime watchdog beside the Chief: loop help, context budgets, status reports.

Detection and reports are deterministic reads of the activity log. The watchdog's
own reasoning provider is invoked only to write guidance for a detected problem.
"""

import asyncio
import copy
import time
from collections import Counter, defaultdict, deque
from typing import TYPE_CHECKING

from pydantic import JsonValue

from ..context import ReasoningProvider
from ..contracts import (
    JSON,
    TERMINAL,
    AgentSpec,
    AgentState,
    AgentTurn,
    AskHuman,
    ContextPacket,
    ContextSpec,
    Finish,
    MessageEnvelope,
    Ref,
    RequestRecord,
    Send,
    Wait,
)
from ..storage import Store
from ..tools.registry import encode

if TYPE_CHECKING:
    from .runtime import Runtime

WATCHDOG = """You are the Guacamole runtime watchdog. You supervise engineering agents;
you never do engineering work, decide, or approve anything. Return exactly one JSON
AgentTurn matching response_schema. Supply a concise rationale; no hidden chain of thought.
state.issues lists agents that need help:
- loop: the agent repeated the same action or had every recent action rejected.
  recent_turns shows its actions, rationales and rejection details. reference_problems
  lists cited Refs that are unknown, mismatched, superseded or stale, with the current
  revision when one exists. Explain why the action keeps failing and name a different
  next action that makes progress. Stale (invalidated) records cannot be read or
  cited; a stale decision requires the Chief to decide a new plan. Repetition that
  is legitimate progress, such as polling a running job, needs no note.
- context: the agent's last prompt used most of its input budget. Tell it to use
  compact with a summary citing the exact refs in largest_optional_sources it no
  longer needs verbatim, and to avoid re-reading summarized material. Pinned material
  cannot be compacted; if nothing optional remains, ask the human.
Act with send: recipient is the issue's agent_id, schema_id Note@1, payload
{"text": ..., "evidence": [...]}, request false, no reply_to. Address each agent once,
in specific, actionable terms with exact refs copied from state. If prior_notes > 0
and the agent is still stuck, use ask_human with blocking false and a focused
question instead. When every issue is addressed, use wait. Use no other actions.
"""


def _reference_problems(store: Store, value: object) -> list[JSON]:
    """Explain each cited Ref that cannot be used as a current reference."""
    if isinstance(value, list):
        return [p for item in value for p in _reference_problems(store, item)]
    if not isinstance(value, dict):
        return []
    try:
        ref = Ref.model_validate(value)
    except ValueError:
        return [p for item in value.values() for p in _reference_problems(store, item)]
    latest = store.maybe(ref.kind, ref.id)
    if latest is None:
        problem = "unknown record"
    else:
        try:
            snapshot = store.resolve(ref)
        except ValueError:
            problem = "revision or sha256 matches no saved revision"
        else:
            if snapshot.stale:
                problem = "stale: invalidated by changed inputs or human input"
            elif snapshot.ref.revision != latest.ref.revision:
                problem = "superseded by a newer revision"
            else:
                return []
    current = latest.ref if latest is not None and not latest.stale else None
    return [
        {
            "ref": value,
            "problem": problem,
            "current": current.model_dump(mode="json") if current else None,
        }
    ]


def _lowest_effort(provider: ReasoningProvider) -> ReasoningProvider:
    """Copy at the lowest reasoning effort; the project's own provider is untouched."""
    low = copy.copy(provider)
    # "low" is the lowest level both the Codex (gpt-6-astra) and Claude CLIs accept.
    # ponytail: providers without an effort setting (Astra API) keep their default.
    if hasattr(low, "effort"):
        setattr(low, "effort", "low")  # noqa: B010 -- effort is outside the provider protocol
    return low


class Watchdog:
    """Supervises a project run at the lowest reasoning effort of its provider.

    reasoning=None reuses the project's provider; either way a low-effort copy is used.
    """

    def __init__(
        self,
        reasoning: ReasoningProvider | None = None,
        *,
        report_interval_s: float = 600.0,
        poll_s: float = 5.0,
        loop_turns: int = 3,
        compact_at: float = 0.85,
    ) -> None:
        if report_interval_s <= 0 or poll_s <= 0:
            raise ValueError("Watchdog intervals must be positive")
        if loop_turns < 2 or not 0 < compact_at <= 1:
            raise ValueError("Watchdog needs loop_turns >= 2 and 0 < compact_at <= 1")
        self.reasoning = reasoning
        self.report_interval_s, self.poll_s = report_interval_s, poll_s
        self.loop_turns, self.compact_at = loop_turns, compact_at

    def start(self, runtime: "Runtime") -> None:
        """Reset per-run tracking; only activity after this point is examined."""
        project = runtime.project
        self.runtime = runtime
        self.provider = _lowest_effort(self.reasoning or runtime.provider)
        self.cursor = project.store.db.execute(
            "SELECT COALESCE(MAX(sequence), 0) FROM events"
        ).fetchone()[0]
        self.started = self.reported = time.monotonic()
        self.turns: defaultdict[str, deque[tuple[str, AgentTurn, str | None]]] = (
            defaultdict(lambda: deque(maxlen=self.loop_turns))
        )
        self.usage: dict[str, tuple[int, int, int, str]] = {}
        self.objectives: dict[str, str] = {}
        self.pressured: set[str] = set()
        self.notes: Counter[str] = Counter()
        self.recent: list[str] = []
        self.tokens = 0
        self.request = project.activity.request(
            RequestRecord(
                run_id=runtime.run_id,
                requester="runtime",
                target="watchdog",
                kind="agent",
                arguments={},
                purpose="Supervise agent loops, context budgets and status reports",
                required=False,
            )
        )
        project.activity.transition(self.request.id, "dispatched", actor="runtime")
        project.activity.transition(self.request.id, "running", actor="runtime")

    def stop(self) -> None:
        activity = self.runtime.project.activity
        if activity.get(self.request.id).status not in TERMINAL:
            activity.transition(self.request.id, "completed", actor="watchdog")

    async def supervise(self) -> None:
        """Poll until cancelled; supervision failures never stop the run."""
        while True:
            await asyncio.sleep(self.poll_s)
            try:
                await self.check()
                if time.monotonic() - self.reported >= self.report_interval_s:
                    self.report()
            except Exception as exc:  # noqa: BLE001 -- recorded, never fatal to the run
                self.runtime.project.store.event(
                    "watchdog",
                    "watchdog.failed",
                    self.request.id,
                    {"error_type": type(exc).__name__},
                    request_id=self.request.id,
                )

    async def check(self) -> None:
        self._scan()
        issues = [*self._loops(), *self._pressure()]
        if issues:
            await self.intervene(issues)

    def _scan(self) -> None:
        """Fold new activity events into per-agent turn and token telemetry."""
        store = self.runtime.project.store
        for event in store.events(after=self.cursor):
            self.cursor = event.sequence
            details = event.details
            if event.type == "provider.dispatched" and "input_tokens" in details:
                used, limit, deferred = (
                    int(str(details[key]))
                    for key in ("input_tokens", "max_input_tokens", "deferred")
                )
                packet = str(details["packet_id"])
                self.usage[event.actor] = (used, limit, deferred, packet)
                self.tokens += used
            elif event.type == "provider.responded":
                turn = store.model("agent_turn", event.entity_id, AgentTurn)
                self.objectives[event.actor] = turn.rationale.objective
                self.turns[event.actor].append((event.entity_id, turn, None))
            elif (
                event.type == "action.rejected"
                and details.get("phase") in {"action", "rationale"}
                and self.turns[event.entity_id]
            ):
                invocation, turn, _ = self.turns[event.entity_id][-1]
                self.turns[event.entity_id][-1] = (
                    invocation,
                    turn,
                    str(details.get("detail")),
                )

    def _status(self, agent_id: str) -> str:
        state = self.runtime.project.store.maybe("agent_state", agent_id)
        return str(state.data["status"]) if state else "unknown"

    def _loops(self) -> list[JSON]:
        store = self.runtime.project.store
        issues: list[JSON] = []
        for agent_id, turns in self.turns.items():
            if len(turns) < self.loop_turns or self._status(agent_id) != "active":
                continue
            actions = {encode(t.action.model_dump(mode="json")) for _, t, _ in turns}
            rejected = all(rejection for _, _, rejection in turns)
            repeated = len(actions) == 1 and turns[0][1].action.kind != "wait"
            if not rejected and not repeated:
                continue
            problems = {
                encode(p): p
                for _, turn, _ in turns
                for p in _reference_problems(store, turn.action.model_dump(mode="json"))
            }
            issues.append(
                {
                    "kind": "loop",
                    "agent_id": agent_id,
                    "task_id": store.get("agent", agent_id).data["task_id"],
                    "pattern": "rejected" if rejected else "repeated",
                    "recent_turns": [
                        {
                            "action": encode(turn.action.model_dump(mode="json"))[
                                :2000
                            ],
                            "objective": turn.rationale.objective[:500],
                            "explanation": turn.rationale.explanation[:1000],
                            "rejected": rejection,
                        }
                        for _, turn, rejection in turns
                    ],
                    "reference_problems": list(problems.values()),
                    "prior_notes": self.notes[agent_id],
                }
            )
            turns.clear()
        return issues

    def _pressure(self) -> list[JSON]:
        store = self.runtime.project.store
        issues: list[JSON] = []
        for agent_id, (used, limit, deferred, packet_id) in self.usage.items():
            if used < self.compact_at * limit:
                self.pressured.discard(agent_id)  # Re-arm after the agent compacts.
                continue
            if agent_id in self.pressured or self._status(agent_id) not in {
                "active",
                "waiting",
            }:
                continue
            self.pressured.add(agent_id)
            agent = store.model("agent", agent_id, AgentSpec)
            packet = store.model("context", packet_id, ContextPacket)
            optional = {*agent.context.selected, *agent.context.summaries}
            sizes = sorted(
                (
                    (len(encode(store.resolve(ref).data)), ref)
                    for ref in packet.sources
                    if ref in optional
                ),
                key=lambda item: item[0],
                reverse=True,
            )
            issues.append(
                {
                    "kind": "context",
                    "agent_id": agent_id,
                    "task_id": agent.task_id,
                    "input_tokens": used,
                    "max_input_tokens": limit,
                    "deferred_items": deferred,
                    "largest_optional_sources": [
                        {"ref": ref.model_dump(mode="json"), "bytes": size}
                        for size, ref in sizes[:10]
                    ],
                    "prior_notes": self.notes[agent_id],
                }
            )
        return issues

    async def intervene(self, issues: list[JSON]) -> None:
        """Let the watchdog's model address the issues with notes or human questions."""
        runtime = self.runtime
        project, store = runtime.project, runtime.project.store
        provider = self.provider
        reserved = 8_000
        spec = AgentSpec(
            id="watchdog",
            task_id="watchdog",
            parent_id=None,
            objective="Keep agents progressing within their context budgets",
            context=ContextSpec(
                max_input_tokens=min(
                    100_000, provider.context_capacity_tokens - reserved
                ),
                reserved_output_tokens=reserved,
            ),
            decision_id=None,
        )
        targets = {str(issue["agent_id"]) for issue in issues}
        self.recent.extend(f"{issue['task_id']} ({issue['kind']})" for issue in issues)
        observation: JSON = {}
        for _ in range(len(issues) + 1):
            packet = await project.contexts.build(
                spec,
                self.request.id,
                provider,
                instructions=WATCHDOG,
                state={
                    "run_id": runtime.run_id,
                    "issues": [*issues],
                    "last_observation": observation,
                },
            )
            turn = AgentTurn.model_validate(await provider.respond(packet))
            context = store.get("context", packet.id).ref
            store.put(
                "agent_turn",
                packet.invocation_id,
                turn,
                actor="watchdog",
                dependencies=(context,),
                request_id=self.request.id,
                allow_stale_dependencies=True,
            )
            action = turn.action
            try:
                if (
                    isinstance(action, Send)
                    and action.recipient in targets
                    and action.schema_id == "Note@1"
                    and not action.request
                    and action.reply_to is None
                ):
                    message = project.activity.deliver(
                        MessageEnvelope(
                            project_id=store.project_id,
                            run_id=runtime.run_id,
                            sender="watchdog",
                            recipient=action.recipient,
                            kind="finding",
                            schema_id="Note@1",
                            payload=action.payload,
                            request_id=self.request.id,
                            context_refs=(context,),
                        )
                    )
                    self.notes[action.recipient] += 1
                    state = store.model("agent_state", action.recipient, AgentState)
                    if state.status == "waiting":
                        recipient = store.model("agent", action.recipient, AgentSpec)
                        runtime._wake(recipient, state, "Watchdog note")
                    observation = {"sent": message.message.id, "to": action.recipient}
                elif isinstance(action, AskHuman):
                    observation = {
                        "asked": project.human.ask(
                            action.model_copy(update={"blocking": False}),
                            run_id=runtime.run_id,
                            sender="watchdog",
                            parent_id=self.request.id,
                            packet_id=packet.id,
                        )
                    }
                elif isinstance(action, (Wait, Finish)):
                    return
                else:
                    observation = {
                        "rejected": "Use send (Note@1 to an issue agent_id), "
                        "ask_human, or wait"
                    }
            except (KeyError, ValueError, PermissionError) as exc:
                observation = {"rejected": type(exc).__name__}

    def report(self) -> JSON:
        """Emit a deterministic watchdog.report event for hosts and subscribers."""
        runtime = self.runtime
        project, store = runtime.project, runtime.project.store
        self._scan()
        self.reported = time.monotonic()
        agents: list[JsonValue] = []
        lines: list[str] = []
        statuses: Counter[str] = Counter()
        for agent in runtime._agents():
            state = store.model("agent_state", agent.id, AgentState)
            statuses[state.status] += 1
            used, limit, deferred, _ = self.usage.get(
                agent.id, (0, agent.context.max_input_tokens, 0, "")
            )
            agents.append(
                {
                    "agent_id": agent.id,
                    "task_id": agent.task_id,
                    "status": state.status,
                    "steps": state.steps,
                    "max_steps": agent.budget.max_steps,
                    "tool_calls": state.tool_calls,
                    "input_tokens": used,
                    "max_input_tokens": limit,
                    "deferred_items": deferred,
                    "objective": self.objectives.get(agent.id, ""),
                }
            )
            lines.append(
                f"- {agent.task_id} [{state.status}] steps {state.steps}/"
                f"{agent.budget.max_steps}, tool calls {state.tool_calls}/"
                f"{agent.budget.max_tool_calls}, context {used:,}/{limit:,} "
                f"({used / limit:.0%}, {deferred} deferred)"
                + (
                    f": {self.objectives[agent.id]}"
                    if agent.id in self.objectives
                    else ""
                )
            )
        human = len(project.human.inbox(run_id=runtime.run_id))
        open_items = sum(
            1 for s in store.list("open_item") if not s.data["resolved_by"] or s.stale
        )
        reviews = [
            f"{s.data['stage']} {s.data['status']}"
            for s in store.list("review")
            if not s.stale
        ]
        minutes = (time.monotonic() - self.started) / 60
        header = (
            f"Watchdog report, run {runtime.run_id} after {minutes:.0f} min: "
            + ", ".join(f"{n} {status}" for status, n in sorted(statuses.items()))
            + f"; {human} pending human requests; {open_items} open items; "
            f"reviews: {', '.join(reviews) or 'none'}; "
            f"{self.tokens:,} input tokens dispatched; "
            f"interventions: {', '.join(self.recent) or 'none'}"
        )
        details: JSON = {
            "run_id": runtime.run_id,
            "elapsed_s": round(minutes * 60, 1),
            "agents": agents,
            "pending_human_requests": human,
            "open_items": open_items,
            "reviews": [*reviews],
            "input_tokens_dispatched": self.tokens,
            "interventions": [*self.recent],
            "text": "\n".join((header, *lines)),
        }
        self.recent = []
        store.event(
            "watchdog",
            "watchdog.report",
            runtime.run_id,
            details,
            request_id=self.request.id,
        )
        return details
