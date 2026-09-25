"""Durable requests and peer inboxes. Only runtime sessions choose senders."""

from datetime import UTC, datetime

from .contracts import (
    JSON,
    TERMINAL,
    AgentSpec,
    Attempt,
    InboxEntry,
    MessageEnvelope,
    RequestRecord,
    Status,
    now,
)
from .storage import Store
from .tools.registry import ToolRegistry, encode


class Activity:
    def __init__(self, store: Store, registry: ToolRegistry) -> None:
        self.store, self.registry = store, registry

    def request(self, record: RequestRecord) -> RequestRecord:
        if self.store.maybe("request", record.id):
            raise ValueError("Request already exists; use an explicit retry")
        if record.parent_id:
            self.get(record.parent_id)
        self.store.put(
            "request",
            record.id,
            record,
            actor=record.requester,
            request_id=record.id,
            event="request.queued",
        )
        return record

    def get(self, id: str) -> RequestRecord:
        return self.store.model("request", id, RequestRecord)

    def requests(
        self,
        *,
        status: Status | None = None,
        agent: str | None = None,
        decision: str | None = None,
    ) -> tuple[RequestRecord, ...]:
        records = tuple(
            RequestRecord.model_validate_json(encode(s.data))
            for s in self.store.list("request")
        )
        return tuple(
            r
            for r in sorted(records, key=lambda r: r.created_at)
            if (status is None or r.status == status)
            and (agent is None or agent in (r.requester, r.target))
            and (decision is None or r.decision_id == decision)
        )

    def transition(
        self,
        id: str,
        status: Status,
        *,
        actor: str,
        reason: str | None = None,
        result: object = None,
    ) -> RequestRecord:
        with self.store.atomic():
            record = self.get(id)
            if record.status in TERMINAL:
                raise ValueError("Terminal request; retry or reconcile explicitly")
            if status == "completed":
                pending = [
                    r.id
                    for r in self.requests()
                    if r.parent_id == id
                    and r.required
                    and r.status not in {"completed", "cancelled"}
                ]
                if pending:
                    raise ValueError(f"Required child requests unresolved: {pending}")
            attempts = record.attempts
            if status == "dispatched":
                if record.status != "queued":
                    raise ValueError("Only queued requests may dispatch")
                attempts += (Attempt(number=len(attempts) + 1),)
            elif status == "running" and record.status != "dispatched":
                raise ValueError("A request must be dispatched before running")
            if attempts:
                update = {"status": status, "reason": reason}
                if status in TERMINAL or status == "blocked":
                    update["finished_at"] = now()
                attempts = (*attempts[:-1], attempts[-1].model_copy(update=update))
            changed = record.model_copy(
                update={
                    "status": status,
                    "attempts": attempts,
                    "reason": reason,
                    "result": result,
                }
            )
            changed = RequestRecord.model_validate(changed)
            self.store.put(
                "request",
                id,
                changed,
                actor=actor,
                request_id=id,
                event=f"request.{status}",
            )
        return changed

    def retry(
        self, id: str, *, actor: str, reason: str, reconcile_uncertain: bool = False
    ) -> RequestRecord:
        record = self.get(id)
        if record.status not in {
            "failed",
            "interrupted",
            "uncertain",
            "blocked",
            "expired",
        }:
            raise ValueError("Request cannot be retried in its current state")
        if record.status == "uncertain" and not reconcile_uncertain:
            raise ValueError("Reconcile the unknown external outcome before retrying")
        if not reason.strip():
            raise ValueError("Retry needs a recorded reason")
        changed = record.model_copy(
            update={"status": "queued", "reason": reason, "result": None}
        )
        self.store.put(
            "request",
            id,
            changed,
            actor=actor,
            request_id=id,
            event="request.retry_requested",
        )
        return changed

    def recover(self) -> None:
        for record in self.requests():
            if record.status in {"dispatched", "running", "cancel_requested"}:
                status = (
                    "uncertain"
                    if record.kind in {"tool", "decision"}
                    else "interrupted"
                )
                self.transition(
                    record.id,
                    status,
                    actor="runtime",
                    reason="Previous execution ended without a persisted outcome; no automatic redispatch",
                )

    def expired(self, id: str) -> bool:
        record = self.get(id)
        if (
            record.deadline is not None
            and datetime.fromisoformat(record.deadline) <= datetime.now(UTC)
            and record.status == "queued"
        ):
            self.transition(
                id, "expired", actor="runtime", reason="Deadline passed before dispatch"
            )
            return True
        return False

    def deliver(self, message: MessageEnvelope) -> InboxEntry:
        """Idempotent delivery; envelopes are built by a trusted session."""
        self.registry.payload(message.schema_id, message.payload)
        existing = self.store.maybe("inbox", message.id)
        if existing:
            entry = InboxEntry.model_validate_json(encode(existing.data))
            if entry.message != message:
                raise ValueError("Message ID reused with different content")
            return entry
        entry = InboxEntry(
            message=message,
            response_required=message.kind in {"request", "delegation", "question"},
        )
        with self.store.atomic():
            self.store.put(
                "message",
                message.id,
                message,
                actor=message.sender,
                request_id=message.request_id,
                event="message.queued",
            )
            self.store.event(
                "runtime",
                "message.dispatched",
                message.id,
                request_id=message.request_id,
            )
            recipient = self.store.maybe("agent", message.recipient)
            state = self.store.maybe("agent_state", message.recipient)
            if (
                recipient is None
                or state is not None
                and state.data["status"] == "completed"
            ):
                entry = entry.model_copy(
                    update={"reason": "Unknown or terminated recipient; undeliverable"}
                )
                event = "message.undeliverable"
            else:
                entry = entry.model_copy(update={"delivered_at": now()})
                event = "message.delivered"
            self.store.put(
                "inbox",
                message.id,
                entry,
                actor="runtime",
                request_id=message.request_id,
                event=event,
            )
        return entry

    def inbox(self, agent_id: str) -> tuple[InboxEntry, ...]:
        entries = (
            InboxEntry.model_validate_json(encode(s.data))
            for s in self.store.list("inbox")
        )
        return tuple(
            sorted(
                (e for e in entries if e.message.recipient == agent_id),
                key=lambda e: e.message.created_at,
            )
        )

    def sent(self, agent_id: str) -> tuple[MessageEnvelope, ...]:
        messages = (
            MessageEnvelope.model_validate_json(encode(s.data))
            for s in self.store.list("message")
        )
        return tuple(
            sorted(
                (m for m in messages if m.sender == agent_id),
                key=lambda m: m.created_at,
            )
        )

    def acknowledge(self, agent_id: str, message_id: str) -> None:
        entry = self.store.model("inbox", message_id, InboxEntry)
        if entry.message.recipient != agent_id or entry.delivered_at is None:
            raise PermissionError(
                "Only the recipient can acknowledge a delivered message"
            )
        if entry.acknowledged_at is None:
            self.store.put(
                "inbox",
                message_id,
                entry.model_copy(update={"acknowledged_at": now()}),
                actor=agent_id,
                request_id=entry.message.request_id,
                event="message.acknowledged",
            )

    def included(self, agent_id: str, message_id: str, packet_id: str) -> None:
        entry = self.store.model("inbox", message_id, InboxEntry)
        if entry.message.recipient != agent_id or entry.delivered_at is None:
            raise PermissionError("Message is not in this agent's inbox")
        if packet_id not in entry.included_packets:
            self.store.put(
                "inbox",
                message_id,
                entry.model_copy(
                    update={"included_packets": (*entry.included_packets, packet_id)}
                ),
                actor="runtime",
                request_id=entry.message.request_id,
                event="message.included_in_context",
            )

    def allow_peer(self, sender: AgentSpec, recipient_id: str) -> None:
        recipient = self.store.model("agent", recipient_id, AgentSpec)
        if sender.parent_id is None or recipient.id == sender.parent_id:
            return
        if (
            recipient.parent_id != sender.parent_id
            or recipient.task_id not in sender.peers
        ):
            raise PermissionError("Peer is outside this agent's communication grants")

    def trace(self, request_id: str) -> JSON:
        self.get(request_id)
        ids = {request_id}
        records = self.requests()
        while True:
            expanded = ids | {r.id for r in records if r.parent_id in ids}
            if expanded == ids:
                break
            ids = expanded
        selected = [r for r in records if r.id in ids]
        linked = (
            ids
            | {r.rationale_id for r in selected}
            | {r.packet_id for r in selected}
            | {r.decision_id for r in selected}
        )
        events = [
            e
            for e in self.store.events()
            if e.request_id in ids or e.entity_id in linked
        ]
        snapshots = [
            s
            for s in self.store.list()
            if s.ref.id in linked or s.data.get("request_id") in ids
        ]
        message_ids = {s.ref.id for s in snapshots if s.ref.kind == "message"}
        snapshots.extend(s for s in self.store.list("inbox") if s.ref.id in message_ids)
        # Include original attempt snapshots, not just the latest request revision.
        snapshots = [
            version
            for s in snapshots
            for version in self.store.history(s.ref.kind, s.ref.id)
        ]
        by_ref = {(s.ref.kind, s.ref.id, s.ref.revision): s for s in snapshots}
        pending = list(snapshots)
        while pending:
            for ref in pending.pop().dependencies:
                key = (ref.kind, ref.id, ref.revision)
                if key not in by_ref:
                    source = self.store.resolve(ref)
                    by_ref[key] = source
                    pending.append(source)
        return {
            "requests": [r.model_dump(mode="json") for r in selected],
            "events": [e.model_dump(mode="json") for e in events],
            "records": [s.model_dump(mode="json") for s in by_ref.values()],
        }
