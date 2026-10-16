"""Terminal notifications for example hosts."""

import asyncio
import os
import sys
from typing import TYPE_CHECKING

from .contracts import TERMINAL, MessageEnvelope, now

if TYPE_CHECKING:
    from .project import Project

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
