"""Terminal hosting for example scripts: preflight, run loop, notifications.

A host script registers its tools, then awaits host(): it runs or resumes the
workspace's project, serves the authenticated loopback control socket, prints
human requests, reviews and agent messages, and waits for each human answer.
"""

import asyncio
import importlib.util
import json
import os
import shutil
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from .contracts import (
    TERMINAL,
    AgentSpec,
    Budget,
    ContextSpec,
    MessageEnvelope,
    ProjectRequest,
    ProjectResult,
    now,
)
from .logo import logo
from .tools.mcp import ToolSession
from .websocket import WebSocketBridge

if TYPE_CHECKING:
    from .project import Project

# The checkout this package was loaded from, when it is installed editable.
REPOSITORY = Path(__file__).resolve().parents[2]


def preflight(
    cli: str, login: str, modules: Iterable[str] = (), install: str = ""
) -> None:
    """Print the logo and stop before any workspace exists if a CLI or module is missing.

    login is the message for a missing cli; install says how to get the modules.
    """
    print(logo, flush=True)
    # uv run installs the source distribution; reuse the checkout's SysML assets.
    venv = REPOSITORY / ".venv/lib"
    for name, pattern in (
        ("GUACAMOLE_SYSML_LIBRARY", "python*/site-packages/sysml/stdlib"),
        ("SYSMLV2_ABI", "python*/site-packages/sysml/_native/libsysmlv2_abi.*"),
    ):
        found = sorted(venv.glob(pattern))
        if found and not os.environ.get(name):
            os.environ[name] = str(found[-1])
    if shutil.which(cli) is None:
        raise SystemExit(login)
    missing = [name for name in modules if importlib.util.find_spec(name) is None]
    if missing:
        raise SystemExit(
            f"Missing example dependencies: {', '.join(missing)}. {install}"
        )


def refresh_limits(
    project: "Project",
    context: ContextSpec,
    budget: Budget,
    run_id: str | None = None,
    worker_max_input_tokens: int | None = None,
) -> ContextSpec:
    """context within the provider's capacity; applied to a saved run on resume.

    A resumed run keeps its saved engineering context; only its input and output
    limits and budget change, for the run, the Chief and the systems engineer.
    Live workers are raised to worker_max_input_tokens when it is given.
    """
    if project.reasoning is None:
        raise ValueError("Configure a reasoning provider before setting run limits")
    capacity = project.reasoning.context_capacity_tokens
    if context.reserved_output_tokens >= capacity:
        raise ValueError("Reserved output leaves no provider capacity for input")
    limits = {
        "max_input_tokens": min(
            context.max_input_tokens, capacity - context.reserved_output_tokens
        ),
        "reserved_output_tokens": context.reserved_output_tokens,
    }
    clamped = context.model_copy(update=limits)
    print(
        f"Context input budget: {clamped.max_input_tokens} "
        f"(configured {context.max_input_tokens}; provider capacity {capacity}; "
        f"reserved output {clamped.reserved_output_tokens})",
        flush=True,
    )
    if run_id is None:
        return clamped
    store = project.store
    run = store.get("run", run_id).data
    saved = ProjectRequest.model_validate_json(json.dumps(run["request"]))
    request = saved.model_copy(
        update={"context": saved.context.model_copy(update=limits), "budget": budget}
    )
    # The Chief and the systems engineer serve the whole run.
    roots = [
        store.model("agent", str(run[key]), AgentSpec)
        for key in ("chief_id", "engineer_id")
        if run.get(key)
    ]
    with store.atomic():
        if request != saved:
            store.put(
                "run",
                run_id,
                run | {"request": request.model_dump(mode="json")},
                actor="script",
                event="run.budgets_updated",
            )
        for agent in roots:
            updated = agent.model_copy(
                update={
                    "context": agent.context.model_copy(update=limits),
                    "budget": budget,
                }
            )
            if updated != agent:
                store.put(
                    "agent",
                    agent.id,
                    updated,
                    actor="script",
                    event="agent.budgets_updated",
                )
        if worker_max_input_tokens is None:
            return clamped
        # The Chief sets worker limits at spawn; raise live ones to the floor.
        for snapshot in store.list("agent"):
            agent = store.model("agent", snapshot.ref.id, AgentSpec)
            state = store.maybe("agent_state", agent.id)
            if agent.id in {r.id for r in roots} or (
                state and state.data.get("status") == "superseded"
            ):
                continue
            floor = min(
                worker_max_input_tokens, capacity - agent.context.reserved_output_tokens
            )
            if agent.context.max_input_tokens < floor:
                store.put(
                    "agent",
                    agent.id,
                    agent.model_copy(
                        update={
                            "context": agent.context.model_copy(
                                update={"max_input_tokens": floor}
                            )
                        }
                    ),
                    actor="script",
                    event="agent.budgets_updated",
                )
    return clamped


async def host(
    project: "Project",
    request: Callable[[ContextSpec], ProjectRequest],
    *,
    port: int,
    context: ContextSpec,
    budget: Budget,
    run_id: str | None = None,
    worker_max_input_tokens: int | None = None,
    reply: str | None = None,
) -> ProjectResult:
    """Run the project, or resume its saved run, until it needs nothing from a human.

    request builds a new run's request from the context within provider limits;
    a saved run is resumed instead (run_id picks one of several). The control
    socket on port stays up throughout. On awaiting_human or awaiting_review it
    waits for the answer or review disposition, then resumes. Each result is
    written to result.json and the timeline to timeline.jsonl in the sandbox.

    Unattended, reply answers every question as it is asked, by author
    "unattended"; review dispositions stay with a human.
    """

    def answer_all() -> int:
        answered = 0
        for entry in project.human.inbox():
            question = project.activity.get(entry.message.request_id or "")
            if reply is None or "review" in question.arguments:
                continue
            try:
                project.human.reply(question.id, reply, author="unattended")
            except ValueError:
                continue  # Answered or withdrawn since the inbox was read.
            answered += 1
        return answered

    async def answering() -> None:
        while True:
            # ponytail: 2 s poll; a reply restarts turns in flight, so answer promptly.
            await asyncio.sleep(2)
            answer_all()

    runs = project.store.list("run")
    if run_id is None and len(runs) > 1:
        raise ValueError("Multiple saved runs: pass the run_id to resume")
    run_id = run_id or (runs[0].ref.id if runs else None)
    limits = refresh_limits(project, context, budget, run_id, worker_max_input_tokens)
    pending = None if run_id else request(limits)
    timeline = project.output_path(Path("timeline.jsonl"))
    bridge = WebSocketBridge(ToolSession(project))
    tasks = [asyncio.create_task(notifications(project))]
    if reply is not None:
        tasks.append(asyncio.create_task(answering()))
    try:
        async with bridge.serve(port=port):
            print(f"Human control: ws://127.0.0.1:{port}", flush=True)
            print(f"Authorization: Bearer {bridge.token}", flush=True)
            print(
                f"Outputs: {project.sandbox}\nSend corrections with interject at any time.",
                flush=True,
            )
            # A run can stop on a non-blocking question before it is answered.
            answers_left = 5
            while True:
                result = await project.run(pending, resume=run_id)
                pending, run_id = None, result.run_id
                print(result.model_dump_json(indent=2), flush=True)
                project.output_path(Path("result.json")).write_text(
                    result.model_dump_json(indent=2), encoding="utf-8"
                )
                project.export(timeline)
                if result.status not in {"awaiting_human", "awaiting_review"}:
                    if (
                        result.status == "paused"
                        or not answers_left
                        or not answer_all()
                    ):
                        return result
                    answers_left -= 1
                    continue
                # Continue once the host records a reply, correction, or review disposition.
                while any(
                    project.activity.get(entry.message.request_id or "").required
                    for entry in project.human.inbox(run_id=run_id)
                ):
                    await asyncio.sleep(0.5)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await project.drain()
        project.export(timeline)


HUMAN, REVIEW, MESSAGE = "1;33", "1;32", "36"  # ANSI: bold yellow, bold green, cyan


def paint(code: str, text: str) -> str:
    """Colour text for a terminal; plain when piped or NO_COLOR is set."""
    if sys.stdout.isatty() and "NO_COLOR" not in os.environ:
        return f"\033[{code}m{text}\033[0m"
    return text


async def notifications(project: "Project") -> None:
    """Print open human requests and reviews and agent messages; log the watchdog.

    On resume, requests and reviews already answered are skipped, and agent messages
    and watchdog output are only shown from launch on. Watchdog reports and notes go
    to watchdog.log in the workspace, outside the agents' sandbox.
    """
    store, cursor, started = project.store, 0, now()
    log = store.directory / "watchdog.log"
    print(f"Watchdog log: {log}", flush=True)

    def name(agent_id: str) -> str:
        agent = store.maybe("agent", agent_id)
        return str(agent.data["task_id"]) if agent else agent_id

    def write(timestamp: str, text: str) -> None:
        with log.open("a", encoding="utf-8") as file:
            file.write(f"{timestamp}\n{text}\n\n")

    while True:
        for event in project.events(after=cursor):
            cursor = event.sequence
            if event.type == "human.requested":
                if project.activity.get(event.entity_id).status not in TERMINAL:
                    print(
                        paint(HUMAN, f"\nHUMAN INPUT [{event.entity_id}] ")
                        + str(event.details["question"]),
                        flush=True,
                    )
            elif event.type == "review.ready":
                if store.get("review", event.entity_id).data["status"] == "ready":
                    print(
                        paint(REVIEW, "\nReview package ready: ")
                        + str(project.sandbox / "reviews" / event.entity_id),
                        flush=True,
                    )
            elif event.timestamp < started:
                continue
            elif event.type == "message.delivered":
                message = store.model("message", event.entity_id, MessageEnvelope)
                # Questions to the human are printed above as HUMAN INPUT.
                if message.recipient == "human":
                    continue
                body = message.payload
                if isinstance(body, dict):
                    body = body.get("text", body)
                header = (
                    f"[{name(message.sender)} -> {name(message.recipient)}] "
                    f"{message.kind}"
                )
                if message.sender == "watchdog":
                    write(event.timestamp, f"{header}\n{body}")
                else:
                    print(f"\n{paint(MESSAGE, header)}\n{body}", flush=True)
            elif event.type == "watchdog.report":
                write(event.timestamp, str(event.details["text"]))
        await asyncio.sleep(0.5)
