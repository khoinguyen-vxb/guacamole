"""Follow a running enclosure project's activity log, read-only, beside the host.

Run with: .venv/bin/python -m examples.enclosure.watch [--all] [--detail] [--tools]

Prints one line per event as it is recorded. Without --all, the high-volume
bookkeeping (message delivery, agent state and context records) is hidden.
With --detail, each agent rationale and every rejection is printed in full.
With --tools, every tool call so far is listed once, then it exits.
"""

import json
import sys
import textwrap
import time
from datetime import datetime

from guacamole import Project

from .enclosure import WORKSPACE

QUIET = (
    "message.dispatched",
    "message.delivered",
    "message.included_in_context",
    "agent_state.recorded",
    "context.saved",
)
RATIONALE = ("objective", "explanation", "assumptions", "alternatives", "uncertainty")


def line(event) -> str:
    when = datetime.fromisoformat(event.timestamp).astimezone().strftime("%H:%M:%S")
    details = event.details if isinstance(event.details, dict) else {}
    extra = {k: v for k, v in details.items() if k not in ("ref", "components")}
    actor = event.actor[:8] if len(event.actor) == 32 else event.actor
    return f"{when} {actor:<16} {event.type:<28} {str(extra)[:110] if extra else ''}"


def indented(text: object) -> str:
    lines = text if isinstance(text, list) else [text]
    return "\n".join(
        textwrap.fill(
            str(item), 100, initial_indent="    - ", subsequent_indent="      "
        )
        for item in lines
        if item
    )


def detail(history: Project, event) -> str | None:
    if event.type == "rationale.recorded":
        content = history.store.get("rationale", event.entity_id).data["content"]
        return "\n".join(
            f"  {key}:\n{indented(content[key])}"
            for key in RATIONALE
            if content.get(key)
        )
    if event.type.endswith(".rejected") or event.type.endswith(".failed"):
        return textwrap.indent(json.dumps(event.details, indent=2), "    ")
    return None


def tool_calls(history: Project) -> None:
    """Every tool call so far: when, which task, which tool, status and arguments."""
    tasks = {
        a.data["id"]: a.data["task_id"]
        for a in history.store.list("agent")
        if isinstance(a.data, dict)
    }
    calls = (r for r in history.activity.requests() if r.kind == "tool")
    for call in sorted(calls, key=lambda r: r.created_at):
        when = datetime.fromisoformat(call.created_at).astimezone().strftime("%H:%M:%S")
        task = tasks.get(call.requester, call.requester[:8])
        arguments = json.dumps(call.arguments)[:80]
        print(f"{when} {task:<18} {call.target:<30} {call.status:<10} {arguments}")


def main() -> None:
    everything, detailed = "--all" in sys.argv, "--detail" in sys.argv
    if "--tools" in sys.argv:
        with Project(WORKSPACE, read_only=True) as history:
            tool_calls(history)
        return
    after = 0
    while True:
        with Project(WORKSPACE, read_only=True) as history:
            for event in history.events(after=after):
                after = event.sequence
                if everything or event.type not in QUIET:
                    print(line(event), flush=True)
                    if detailed and (text := detail(history, event)):
                        print(text, flush=True)
        time.sleep(2)


if __name__ == "__main__":
    main()
