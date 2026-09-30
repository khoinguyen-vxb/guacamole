"""Persistent human questions and corrections, using the project inbox and history."""

from typing import TYPE_CHECKING

from .contracts import (
    TERMINAL,
    AgentSpec,
    AgentState,
    AskHuman,
    HumanInput,
    HumanInputs,
    InboxEntry,
    MessageEnvelope,
    Note,
    Ref,
    RequestRecord,
)
from .tools.registry import encode

if TYPE_CHECKING:
    from .project import Project


class Humans:
    def __init__(self, project: "Project") -> None:
        self.project = project

    def version(self, run_id: str) -> int:
        saved = self.project.store.maybe("human_inputs", run_id)
        return saved.ref.revision if saved else 0

    def references(self, run_id: str) -> tuple[Ref, ...]:
        saved = self.project.store.maybe("human_inputs", run_id)
        return (
            HumanInputs.model_validate_json(encode(saved.data)).sources if saved else ()
        )

    def inbox(
        self, *, run_id: str | None = None, pending_only: bool = True
    ) -> tuple[InboxEntry, ...]:
        activity = self.project.activity
        return tuple(
            entry
            for entry in activity.inbox("human")
            if (run_id is None or entry.message.run_id == run_id)
            and (
                not pending_only
                or activity.get(entry.message.request_id or "").status not in TERMINAL
            )
        )

    def ask(
        self,
        question: AskHuman,
        *,
        run_id: str,
        sender: str,
        parent_id: str | None = None,
        decision_id: str | None = None,
        packet_id: str | None = None,
        rationale_id: str | None = None,
        review: Ref | None = None,
    ) -> str:
        question = AskHuman.model_validate(question)
        project, store = self.project, self.project.store
        for ref in question.references:
            store.resolve(ref, current=True)
        arguments = question.model_dump(mode="json")
        if review is not None:
            store.resolve(review, current=True)
            arguments["review"] = review.model_dump(mode="json")
        with store.atomic():
            request = project.activity.request(
                RequestRecord(
                    run_id=run_id,
                    requester=sender,
                    target="human",
                    kind="human",
                    arguments=arguments,
                    purpose=question.question,
                    parent_id=parent_id,
                    decision_id=decision_id,
                    packet_id=packet_id,
                    rationale_id=rationale_id,
                    required=question.blocking,
                )
            )
            project.activity.transition(request.id, "dispatched", actor="runtime")
            project.activity.deliver(
                MessageEnvelope(
                    id=request.id,
                    project_id=store.project_id,
                    run_id=run_id,
                    sender=sender,
                    recipient="human",
                    kind="question",
                    schema_id="AskHuman@1",
                    payload=question.model_dump(mode="json"),
                    request_id=request.id,
                    parent_request_id=parent_id,
                    context_refs=question.references,
                )
            )
            project.activity.transition(
                request.id, "blocked", actor="runtime", reason="Awaiting human response"
            )
            store.event(
                "runtime",
                "human.requested",
                request.id,
                {
                    "question": question.question,
                    "choices": list(question.choices),
                    "run_id": run_id,
                    "blocking": question.blocking,
                    "review": review.model_dump(mode="json") if review else None,
                },
                request_id=request.id,
            )
        return request.id

    def _answer(
        self,
        request: RequestRecord,
        *,
        author: str,
        text: str,
        references: tuple[Ref, ...],
    ) -> None:
        store, activity = self.project.store, self.project.activity
        message = MessageEnvelope(
            project_id=store.project_id,
            run_id=request.run_id,
            sender=f"human:{author}",
            recipient=request.requester,
            kind="reply",
            schema_id="Note@1",
            payload=Note(text=text, evidence=references).model_dump(mode="json"),
            request_id=request.id,
            parent_request_id=request.parent_id,
            reply_to=request.id,
            context_refs=references,
        )
        activity.deliver(message)
        activity.transition(
            request.id, "completed", actor=message.sender, result=message.payload
        )
        entry = store.model("inbox", request.id, InboxEntry)
        store.put(
            "inbox",
            request.id,
            entry.model_copy(update={"response_message_id": message.id}),
            actor=message.sender,
            request_id=request.id,
            event="message.answered",
        )

    def reply(self, request_id: str, text: str, *, author: str) -> Ref:
        request = self.project.activity.get(request_id)
        if request.kind != "human" or request.status in TERMINAL:
            raise ValueError("Reply requires a pending human request")
        if "review" in request.arguments:
            raise ValueError(
                "Use reviews.accept for review disposition, or interject corrections"
            )
        return self.interject(
            text, author=author, run_id=request.run_id, reply_to=request_id
        )

    def interject(
        self,
        text: str,
        *,
        author: str,
        run_id: str | None = None,
        references: tuple[Ref, ...] = (),
        reply_to: str | None = None,
    ) -> Ref:
        project, store = self.project, self.project.store
        if run_id is None:
            run_id = project.runtime.run_id if project.runtime else None
        if not run_id:
            raise ValueError("Supply a run_id when no project run is active")
        run = store.maybe("run", run_id)
        if run is None and run_id != "script":
            raise ValueError("Unknown project run")
        note = HumanInput(
            run_id=run_id,
            author=author,
            text=text,
            references=references,
            reply_to=reply_to,
        )
        for ref in references:
            store.resolve(ref)
        reply = project.activity.get(reply_to) if reply_to else None
        if reply and (
            reply.kind != "human"
            or reply.run_id != run_id
            or reply.status in TERMINAL
            or "review" in reply.arguments
        ):
            raise ValueError("Reply requires a pending question in this run")
        actor = f"human:{author}"
        with store.atomic():
            source = store.put(
                "source",
                note.id,
                note,
                actor=actor,
                request_id=reply_to,
                event="human.input_recorded",
            )
            store.put(
                "human_inputs",
                run_id,
                HumanInputs(sources=(*self.references(run_id), source)),
                actor=actor,
                request_id=reply_to,
                event="human.interjected",
            )
            if reply:
                self._answer(reply, author=author, text=text, references=(source,))
            agents = []
            for snapshot in store.list("agent"):
                state = store.model("agent_state", snapshot.ref.id, AgentState)
                if project.activity.get(state.request_id).run_id == run_id:
                    agents.append(
                        (store.model("agent", snapshot.ref.id, AgentSpec), state)
                    )
            plans = {
                agent.decision_id
                for agent, state in agents
                if agent.parent_id is None
                or state.status not in {"completed", "superseded"}
            }
            if reply:
                plans.add(reply.decision_id)
            for ref in references:
                if ref.kind == "review":
                    plans.add(str(store.resolve(ref).data["plan_decision"]))
                elif ref.kind == "decision":
                    plans.add(ref.id)
            for decision_id in plans:
                if decision_id is None:
                    continue
                store.invalidate(
                    store.get("decision", decision_id).ref,
                    actor=actor,
                    reason=f"Human input {source.id}",
                )

            # Superseded reasoning can be replaced; launched tools retain their actual status.
            for request in project.requests():
                if request.run_id != run_id or request.status in TERMINAL:
                    continue
                if request.kind in {"agent", "peer", "human"}:
                    project.activity.transition(
                        request.id,
                        "cancelled",
                        actor=actor,
                        reason=f"Superseded by human input {source.id}",
                    )
                elif request.kind == "tool":
                    store.put(
                        "request",
                        request.id,
                        request.model_copy(update={"required": False}),
                        actor=actor,
                        request_id=request.id,
                        event="request.superseded",
                    )
            for agent, state in agents:
                if agent.parent_id is not None:
                    if state.status != "completed":
                        store.put(
                            "agent_state",
                            agent.id,
                            state.model_copy(update={"status": "superseded"}),
                            actor=actor,
                        )
                    continue

                def current(refs: tuple[Ref, ...]) -> tuple[Ref, ...]:
                    return tuple(
                        ref
                        for ref in refs
                        if ref.kind != "decision"
                        and not store.resolve(ref).stale
                        and store.get(ref.kind, ref.id).ref
                        == ref.model_copy(update={"locator": ""})
                    )

                context = agent.context.model_copy(
                    update={
                        "pinned": current(agent.context.pinned),
                        "selected": current(agent.context.selected),
                        "summaries": current(agent.context.summaries),
                    }
                )
                chief = agent.model_copy(
                    update={
                        "decision_id": None,
                        "context": context,
                        "tools": tuple(t.grant for t in project.tools.definitions()),
                    }
                )
                request = project.activity.request(
                    RequestRecord(
                        run_id=run_id,
                        requester=actor,
                        target=chief.id,
                        kind="agent",
                        arguments=chief.model_dump(mode="json"),
                        purpose="Incorporate human corrections and replan",
                        parent_id=state.request_id,
                    )
                )
                store.put(
                    "agent",
                    chief.id,
                    chief,
                    actor=actor,
                    request_id=request.id,
                    event="agent.human_redirected",
                )
                store.put(
                    "agent_state",
                    chief.id,
                    AgentState(
                        request_id=request.id,
                        observation={"human_input": source.model_dump(mode="json")},
                    ),
                    actor=actor,
                )
                project.activity.deliver(
                    MessageEnvelope(
                        project_id=store.project_id,
                        run_id=run_id,
                        sender=actor,
                        recipient=chief.id,
                        kind="finding",
                        schema_id="Note@1",
                        payload=Note(text=text, evidence=(source,)).model_dump(
                            mode="json"
                        ),
                        request_id=request.id,
                        context_refs=(source,),
                    )
                )
            if run:
                store.put(
                    "run",
                    run_id,
                    {**run.data, "status": "incomplete", "result": None},
                    actor=actor,
                )
        return source

    def review_answered(self, ref: Ref, *, author: str, disposition: str) -> None:
        with self.project.store.atomic():
            for entry in self.inbox():
                request = self.project.activity.get(entry.message.request_id or "")
                if request.arguments.get("review") == ref.model_dump(mode="json"):
                    self._answer(
                        request, author=author, text=disposition, references=(ref,)
                    )
