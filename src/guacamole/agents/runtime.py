"""One cooperative runtime for the Chief and task-defined workers."""

import asyncio
import time
from pathlib import Path

from pydantic import Field

from ..context import ContextOverflow, ReasoningProvider
from ..contracts import (
    JSON,
    Acknowledge,
    AgentSpec,
    AgentTurn,
    Compact,
    ContextPacket,
    Decide,
    Deliver,
    Deliverable,
    Extract,
    Finish,
    InboxEntry,
    MessageEnvelope,
    Model,
    Note,
    OpenItem,
    ProjectRequest,
    ProjectResult,
    Publish,
    RationaleRecord,
    Read,
    Record,
    RequestRecord,
    Requirement,
    Retry,
    Review,
    Send,
    Spawn,
    TaskReport,
    ToolCall,
    Verify,
    Wait,
    uid,
)
from ..decision import DecisionBlocked
from ..project import Project
from ..tools.registry import encode
from .chief import CHIEF, COMMON


class AgentState(Model):
    request_id: str
    status: str = "active"
    steps: int = 0
    tool_calls: int = 0
    elapsed_s: float = 0.0
    observation: JSON = Field(default_factory=dict)


class Runtime:
    def __init__(self, project: Project, provider: ReasoningProvider) -> None:
        self.project, self.provider = project, provider
        self.run_id = ""
        self.chief_id = ""
        self.request: ProjectRequest

    def _agents(self) -> tuple[AgentSpec, ...]:
        agents = (
            AgentSpec.model_validate_json(encode(s.data))
            for s in self.project.store.list("agent")
            if self.project.activity.get(
                self.project.store.model("agent_state", s.ref.id, AgentState).request_id
            ).run_id
            == self.run_id
        )
        return tuple(
            sorted(
                agents,
                key=lambda a: (
                    a.parent_id is not None,
                    self.project.activity.get(
                        self.project.store.model(
                            "agent_state", a.id, AgentState
                        ).request_id
                    ).created_at,
                ),
            )
        )

    def _save_state(self, agent: AgentSpec, state: AgentState) -> None:
        self.project.store.put(
            "agent_state", agent.id, state, actor="runtime", request_id=state.request_id
        )

    def _wake(self, agent: AgentSpec, state: AgentState, reason: str) -> None:
        record = self.project.activity.get(state.request_id)
        if record.status == "blocked":
            self.project.activity.retry(record.id, actor="runtime", reason=reason)
        self._save_state(agent, state.model_copy(update={"status": "active"}))

    def _add_agent(self, agent: AgentSpec, *, parent_request: str | None) -> None:
        store = self.project.store
        with store.atomic():
            request = self.project.activity.request(
                RequestRecord(
                    run_id=self.run_id,
                    requester=agent.parent_id or "script",
                    target=agent.id,
                    kind="agent",
                    arguments=agent.model_dump(mode="json"),
                    purpose=agent.objective,
                    parent_id=parent_request,
                    decision_id=agent.decision_id,
                )
            )
            store.put(
                "agent",
                agent.id,
                agent,
                actor=agent.parent_id or "script",
                request_id=request.id,
                event="agent.spawned",
            )
            self._save_state(agent, AgentState(request_id=request.id))
            self.project.activity.deliver(
                MessageEnvelope(
                    project_id=store.project_id,
                    run_id=self.run_id,
                    sender=agent.parent_id or "script",
                    recipient=agent.id,
                    kind="delegation",
                    schema_id="Note@1",
                    payload=Note(text=agent.objective).model_dump(mode="json"),
                    request_id=request.id,
                    parent_request_id=parent_request,
                )
            )

    async def run(
        self, request: ProjectRequest | None, *, resume: str | None
    ) -> ProjectResult:
        store = self.project.store
        if resume is None:
            if request is None:
                raise ValueError(
                    "Supply a ProjectRequest or an explicit run ID to resume"
                )
            self.request, self.run_id = ProjectRequest.model_validate(request), uid()
            work = self.project.output_path(Path("work"))
            work.mkdir(exist_ok=True)
            brief = self.project.output_path(work / f"brief-{self.run_id}.txt")
            brief.write_text(request.description, encoding="utf-8")
            sources = [self.project.ingest(brief, source_id="brief")]
            for path in request.documents:
                ref = self.project.ingest(path)
                sources.append(ref)
                if store.get("source", ref.id).data.get("text") is None:
                    self.project.record_open_item(
                        OpenItem(
                            id=f"reader:{ref.id}",
                            description=f"Source {path.name} requires a supplied reader; original preserved",
                            kind="missing_tool",
                        )
                    )
            context = request.context.model_copy(
                update={
                    "pinned": (*request.context.pinned, sources[0]),
                    "selected": (*request.context.selected, *sources[1:]),
                }
            )
            chief = AgentSpec(
                task_id="chief",
                parent_id=None,
                objective=request.description,
                context=context,
                decision_id=None,
                tools=tuple(t.grant for t in self.project.tools.definitions()),
                budget=request.budget,
            )
            self.chief_id = chief.id
            store.put(
                "run",
                self.run_id,
                {
                    "request": request.model_dump(mode="json"),
                    "chief_id": chief.id,
                    "status": "running",
                },
                actor="script",
            )
            self._add_agent(chief, parent_request=None)
        else:
            if request is not None:
                raise ValueError(
                    "Resume uses the persisted request; record changes explicitly"
                )
            self.run_id = resume
            run = store.get("run", resume).data
            self.request = ProjectRequest.model_validate_json(encode(run["request"]))
            self.chief_id = str(run["chief_id"])
            for agent in self._agents():
                state = store.model("agent_state", agent.id, AgentState)
                record = self.project.activity.get(state.request_id)
                if record.status in {"interrupted", "blocked"}:
                    self.project.activity.retry(
                        record.id,
                        actor="script",
                        reason="Explicit resume of agent reasoning; tools are not replayed",
                    )
                if record.status != "completed":
                    self._save_state(
                        agent, state.model_copy(update={"status": "active"})
                    )
        start = time.monotonic()
        self.deadline = start + self.request.budget.max_seconds
        try:
            while time.monotonic() - start < self.request.budget.max_seconds:
                progressed = False
                for agent in self._agents():
                    state = store.model("agent_state", agent.id, AgentState)
                    if state.status != "active":
                        continue
                    progressed = True
                    await self.step(agent, state)
                if not progressed:
                    break
        except asyncio.CancelledError:
            for agent in self._agents():
                state = store.model("agent_state", agent.id, AgentState)
                if self.project.activity.get(state.request_id).status in {
                    "running",
                    "dispatched",
                }:
                    self.project.activity.transition(
                        state.request_id,
                        "interrupted",
                        actor="runtime",
                        reason="Project run interrupted",
                    )
            raise
        reviews = tuple(s.ref for s in store.list("review") if not s.stale)
        accepted = all(
            self.project.reviews.accepted(stage)
            for stage in self.request.target_reviews
        )
        awaiting = any(
            store.get("review", r.id).data["status"] == "ready" for r in reviews
        )
        open_items = [
            str(s.data["description"])
            for s in store.list("open_item")
            if not s.data["resolved_by"] or s.stale
        ]
        for agent in self._agents():
            state = store.model("agent_state", agent.id, AgentState)
            if state.status not in {"completed"}:
                open_items.append(
                    f"{agent.task_id}: {state.status}: {encode(state.observation)}"
                )
        result = ProjectResult(
            run_id=self.run_id,
            status="complete"
            if accepted
            and all(
                r.status in {"completed", "cancelled"}
                for r in self.project.requests()
                if r.run_id == self.run_id and r.required
            )
            else "awaiting_review"
            if awaiting
            else "incomplete",
            reviews=reviews,
            open_items=tuple(open_items),
            test_only=bool(
                self.project.decisions.provider
                and self.project.decisions.provider.is_test_double
            ),
        )
        store.put(
            "run",
            self.run_id,
            {
                "request": self.request.model_dump(mode="json"),
                "chief_id": self.chief_id,
                "status": result.status,
                "result": result.model_dump(mode="json"),
            },
            actor="runtime",
        )
        return result

    def _context_state(self, agent: AgentSpec, state: AgentState) -> JSON:
        store = self.project.store
        return {
            "run_id": self.run_id,
            "workspace": str(store.directory),
            "sandbox": str(self.project.sandbox),
            "last_observation": state.observation,
            "agents": [
                {
                    "id": a.id,
                    "task_id": a.task_id,
                    "status": store.get("agent_state", a.id).data["status"],
                }
                for a in self._agents()
            ],
            "records": [
                {"ref": s.ref.model_dump(mode="json"), "stale": s.stale}
                for s in store.list()
                if s.ref.kind
                in {
                    "source",
                    "requirement",
                    "open_item",
                    "decision",
                    "artifact",
                    "evidence",
                    "deliverable",
                    "review",
                    "summary",
                    "tool_result",
                    "job_inputs",
                }
            ],
            "requests": [
                {
                    "id": r.id,
                    "target": r.target,
                    "kind": r.kind,
                    "status": r.status,
                    "parent_id": r.parent_id,
                    "reason": r.reason,
                }
                for r in self.project.activity.requests()
                if r.run_id == self.run_id
            ],
            "catalogue": [
                t.model_dump(mode="json") for t in self.project.tools.definitions()
            ]
            if agent.id == self.chief_id
            else [],
            "reviews": [
                {
                    "ref": s.ref.model_dump(mode="json"),
                    "stage": s.data["stage"],
                    "status": s.data["status"],
                    "stale": s.stale,
                }
                for s in store.list("review")
            ],
        }

    async def step(self, agent: AgentSpec, state: AgentState) -> None:
        activity, store = self.project.activity, self.project.store
        record = activity.get(state.request_id)
        if (
            state.steps >= agent.budget.max_steps
            or state.elapsed_s >= agent.budget.max_seconds
        ):
            self._save_state(
                agent,
                state.model_copy(
                    update={
                        "status": "budget_exhausted",
                        "observation": {"reason": "Agent budget exhausted"},
                    }
                ),
            )
            if record.status not in {"blocked", "completed"}:
                activity.transition(
                    record.id,
                    "blocked",
                    actor="runtime",
                    reason="Agent budget exhausted",
                )
            return
        if record.status == "queued":
            activity.transition(record.id, "dispatched", actor="runtime")
            activity.transition(record.id, "running", actor="runtime")
        started = time.monotonic()
        phase = "context"
        changed = state.model_copy(update={"steps": state.steps + 1})
        self._save_state(agent, changed)
        try:
            # Pin current requirements on every invocation; previous snapshots remain saved.
            pins = tuple(s.ref for s in store.list("requirement"))
            actual = agent.model_copy(
                update={
                    "context": agent.context.model_copy(
                        update={
                            "pinned": tuple(
                                dict.fromkeys((*agent.context.pinned, *pins))
                            )
                        }
                    )
                }
            )
            async with asyncio.timeout(
                min(
                    agent.budget.max_seconds - state.elapsed_s,
                    self.deadline - time.monotonic(),
                )
            ):
                packet = await self.project.contexts.build(
                    actual,
                    state.request_id,
                    self.provider,
                    instructions=CHIEF if agent.id == self.chief_id else COMMON,
                    state=self._context_state(agent, state),
                )
                store.event(
                    agent.id,
                    "provider.dispatched",
                    packet.invocation_id,
                    {
                        "packet_id": packet.id,
                        "provider": self.provider.name,
                        "model": self.provider.model,
                    },
                    request_id=state.request_id,
                )
                phase = "provider"
                turn = AgentTurn.model_validate(await self.provider.respond(packet))
                store.put(
                    "agent_turn",
                    packet.invocation_id,
                    turn,
                    actor=agent.id,
                    dependencies=(store.get("context", packet.id).ref,),
                    request_id=state.request_id,
                    event="provider.responded",
                )
                rationale = RationaleRecord(
                    author=agent.id,
                    invocation_id=packet.invocation_id,
                    packet_id=packet.id,
                    request_id=state.request_id,
                    content=turn.rationale,
                )
                store.put(
                    "rationale",
                    rationale.id,
                    rationale,
                    actor=agent.id,
                    dependencies=turn.rationale.evidence,
                    request_id=state.request_id,
                )
                if turn.provider_summary:
                    summary = rationale.model_copy(
                        update={
                            "id": uid(),
                            "origin": "provider_summary",
                            "content": turn.rationale.model_copy(
                                update={"explanation": turn.provider_summary}
                            ),
                        }
                    )
                    store.put(
                        "rationale",
                        summary.id,
                        summary,
                        actor=agent.id,
                        request_id=state.request_id,
                    )
                if isinstance(turn.action, (ToolCall, Retry)):
                    changed = changed.model_copy(
                        update={"tool_calls": state.tool_calls + 1}
                    )
                    self._save_state(agent, changed)
                phase = "action"
                observation, status = await self.act(
                    agent, changed, turn, packet, rationale.id
                )
                changed = changed.model_copy(
                    update={"observation": observation, "status": status}
                )
                if status == "waiting":
                    activity.transition(
                        state.request_id,
                        "blocked",
                        actor="runtime",
                        reason=str(observation.get("reason", "Awaiting human review")),
                    )
        except TimeoutError:
            reason = "Invocation timed out; dispatched tools may still be running"
            changed = changed.model_copy(
                update={"status": "blocked", "observation": {"reason": reason}}
            )
            activity.transition(
                state.request_id, "blocked", actor="runtime", reason=reason
            )
        except (ContextOverflow, DecisionBlocked) as exc:
            changed = changed.model_copy(
                update={
                    "status": "blocked",
                    "observation": {"reason": str(exc) or type(exc).__name__},
                }
            )
            activity.transition(
                state.request_id,
                "blocked",
                actor="runtime",
                reason=str(exc) or type(exc).__name__,
            )
        except Exception as exc:  # noqa: BLE001 -- persist provider/tool failures for correction
            # The next turn can correct a rejected proposal; failed tool work stays visible.
            changed = changed.model_copy(
                update={
                    "observation": {
                        "error_type": type(exc).__name__,
                        "phase": phase,
                        "detail": "Action rejected; inspect request records. Exception text omitted.",
                    }
                }
            )
            if phase != "action":
                changed = changed.model_copy(update={"status": "blocked"})
                activity.transition(
                    state.request_id,
                    "blocked",
                    actor="runtime",
                    reason=f"{phase} failed: {type(exc).__name__}; detail omitted",
                )
            store.event(
                "runtime",
                "action.rejected",
                agent.id,
                changed.observation,
                request_id=state.request_id,
            )
        finally:
            changed = changed.model_copy(
                update={"elapsed_s": state.elapsed_s + time.monotonic() - started}
            )
            self._save_state(agent, changed)

    async def act(
        self,
        agent: AgentSpec,
        state: AgentState,
        turn: AgentTurn,
        packet: ContextPacket,
        rationale_id: str,
    ) -> tuple[JSON, str]:
        action, project = turn.action, self.project
        store, activity = project.store, project.activity
        is_chief = agent.id == self.chief_id
        if isinstance(action, (Decide, Spawn, Record, Review)) and not is_chief:
            raise PermissionError("Only the Chief has this operation")
        match action:
            case Retry():
                if state.tool_calls > agent.budget.max_tool_calls:
                    raise PermissionError("Tool budget exhausted")
                job = project.executor.retry(
                    action.request_id, actor=agent.id, reason=action.reason
                )
                await job.collect()
                return {"request_id": job.id, "result": job.record.result}, "active"
            case ToolCall():
                if (
                    state.tool_calls > agent.budget.max_tool_calls
                    or agent.decision_id is None
                ):
                    raise PermissionError("Tool budget or approved plan is missing")
                job = project.executor.submit(
                    project.tools.get(action.tool),
                    action.arguments,
                    actor=agent.id,
                    grants=agent.tools,
                    run_id=self.run_id,
                    parent_id=state.request_id,
                    decision_id=agent.decision_id,
                    rationale_id=rationale_id,
                    packet_id=packet.id,
                    inputs=action.inputs,
                )
                await job.collect()
                return {
                    "request_id": job.id,
                    "result": job.record.result,
                    "ref": store.get("tool_result", job.id).ref.model_dump(mode="json"),
                }, "active"
            case Decide():
                decision = await project.decisions.choose(
                    action.request,
                    actor=agent.id,
                    run_id=self.run_id,
                    parent_id=state.request_id,
                    rationale_id=rationale_id,
                    packet_id=packet.id,
                )
                if action.request.kind == "work_plan":
                    plan = project.decisions.plan(decision)
                    pins = tuple(
                        r for r in agent.context.pinned if r.kind != "decision"
                    )
                    updated = agent.model_copy(
                        update={
                            "decision_id": decision,
                            "tools": plan.chief_tools,
                            "context": agent.context.model_copy(
                                update={
                                    "pinned": (
                                        *pins,
                                        store.get("decision", decision).ref,
                                    )
                                }
                            ),
                        }
                    )
                    store.put(
                        "agent",
                        agent.id,
                        updated,
                        actor="runtime",
                        request_id=state.request_id,
                        event="agent.plan_assigned",
                    )
                return {
                    "decision_id": decision,
                    "ref": store.get("decision", decision).ref.model_dump(mode="json"),
                }, "active"
            case Spawn():
                plan = project.decisions.plan(action.decision_id)
                task = next(t for t in plan.tasks if t.id == action.task_id)
                agents = self._agents()
                if len(agents) - 1 >= self.request.budget.max_agents:
                    raise PermissionError("Project agent limit reached")
                if any(
                    a.task_id == task.id and a.decision_id == action.decision_id
                    for a in agents
                ):
                    raise ValueError("Task already has a worker")
                for dependency in task.depends_on:
                    if not any(
                        a.task_id == dependency
                        and a.decision_id == action.decision_id
                        and activity.get(
                            store.model("agent_state", a.id, AgentState).request_id
                        ).status
                        == "completed"
                        for a in agents
                    ):
                        raise ValueError(f"Dependency is not complete: {dependency}")
                if (
                    task.budget.max_steps > self.request.budget.max_steps
                    or task.budget.max_tool_calls > self.request.budget.max_tool_calls
                    or task.budget.max_seconds > self.request.budget.max_seconds
                ):
                    raise PermissionError("Worker budget exceeds user limits")
                context = action.context or self.request.context
                pins = (
                    *context.pinned,
                    *plan.inputs,
                    store.get("decision", action.decision_id).ref,
                )
                context = context.model_copy(
                    update={
                        "instructions": self.request.context.instructions
                        + "\n"
                        + context.instructions,
                        "pinned": tuple(dict.fromkeys(pins)),
                    }
                )
                worker = AgentSpec(
                    task_id=task.id,
                    parent_id=agent.id,
                    objective=task.objective,
                    context=context,
                    decision_id=action.decision_id,
                    tools=task.tools,
                    result_schema=task.result_schema,
                    completion_criteria=task.completion_criteria,
                    peers=task.peers,
                    budget=task.budget,
                )
                self._add_agent(worker, parent_request=state.request_id)
                return {"agent_id": worker.id}, "active"
            case Send():
                activity.allow_peer(agent, action.recipient)
                project.tools.payload(action.schema_id, action.payload)
                parent_message = (
                    store.model("message", action.reply_to, MessageEnvelope)
                    if action.reply_to
                    else None
                )
                if parent_message and (
                    parent_message.recipient != agent.id
                    or parent_message.sender != action.recipient
                ):
                    raise PermissionError(
                        "Reply must answer an incoming message from this recipient"
                    )
                request_id = parent_message.request_id if parent_message else None
                with store.atomic():
                    if action.request:
                        request = activity.request(
                            RequestRecord(
                                run_id=self.run_id,
                                requester=agent.id,
                                target=action.recipient,
                                kind="peer",
                                arguments={
                                    "schema_id": action.schema_id,
                                    "payload": action.payload,
                                },
                                purpose=turn.rationale.objective,
                                parent_id=state.request_id,
                                decision_id=agent.decision_id,
                                rationale_id=rationale_id,
                                packet_id=packet.id,
                            )
                        )
                        request_id = request.id
                        activity.transition(request_id, "dispatched", actor="runtime")
                    message = MessageEnvelope(
                        project_id=store.project_id,
                        run_id=self.run_id,
                        sender=agent.id,
                        recipient=action.recipient,
                        kind="reply"
                        if parent_message
                        else "request"
                        if action.request
                        else "finding",
                        schema_id=action.schema_id,
                        payload=action.payload,
                        request_id=request_id,
                        parent_request_id=activity.get(request_id).parent_id
                        if request_id
                        else state.request_id,
                        reply_to=action.reply_to,
                        context_refs=(store.get("context", packet.id).ref,),
                    )
                    delivered = activity.deliver(message)
                    if (
                        delivered.delivered_at is None
                        and request_id
                        and not parent_message
                    ):
                        activity.transition(
                            request_id,
                            "blocked",
                            actor="runtime",
                            reason=delivered.reason,
                        )
                    if parent_message and request_id:
                        pending = activity.get(request_id)
                        if pending.kind != "peer":
                            raise ValueError("Use finish to close an assigned task")
                        activity.transition(
                            request_id,
                            "completed",
                            actor=agent.id,
                            result=action.payload,
                        )
                        entry = store.model("inbox", parent_message.id, InboxEntry)
                        store.put(
                            "inbox",
                            parent_message.id,
                            entry.model_copy(
                                update={"response_message_id": message.id}
                            ),
                            actor=agent.id,
                            request_id=request_id,
                            event="message.answered",
                        )
                peer = store.model("agent_state", action.recipient, AgentState)
                if peer.status == "waiting":
                    recipient = store.model("agent", action.recipient, AgentSpec)
                    self._wake(recipient, peer, "Incoming peer message")
                return {"message_id": message.id, "request_id": request_id}, "active"
            case Acknowledge():
                activity.acknowledge(agent.id, action.message_id)
                return {"acknowledged": action.message_id}, "active"
            case Record():
                if isinstance(action.record, Requirement):
                    ref = project.record_requirement(action.record, actor=agent.id)
                else:
                    ref = project.record_open_item(action.record, actor=agent.id)
                return {"ref": ref.model_dump(mode="json")}, "active"
            case Read():
                refs = (*action.refs, *project.contexts.search(action.search))
                # Selection goes through next packet's budget; never smuggle raw data into state.
                context = agent.context.model_copy(
                    update={
                        "selected": tuple(
                            dict.fromkeys((*agent.context.selected, *refs))
                        )
                    }
                )
                store.put(
                    "agent",
                    agent.id,
                    agent.model_copy(update={"context": context}),
                    actor="runtime",
                )
                return {"selected": [r.model_dump(mode="json") for r in refs]}, "active"
            case Compact():
                ref = project.summarize(action.summary, actor=agent.id)
                context = agent.context.model_copy(
                    update={
                        "summaries": (*agent.context.summaries, ref),
                        "selected": tuple(
                            r
                            for r in agent.context.selected
                            if r not in action.summary.sources
                        ),
                    }
                )
                store.put(
                    "agent",
                    agent.id,
                    agent.model_copy(update={"context": context}),
                    actor="runtime",
                )
                return {"summary": ref.model_dump(mode="json")}, "active"
            case Extract():
                ref = project.extract(action.tool_request, actor=agent.id)
                return {"ref": ref.model_dump(mode="json")}, "active"
            case Publish():
                if agent.decision_id is None:
                    raise PermissionError("Missing governing plan")
                ref = project.publish(
                    path=action.path,
                    artifact_id=action.artifact_id,
                    kind=action.artifact_kind,
                    request_id=action.tool_request,
                    decision_id=agent.decision_id,
                    inputs=action.inputs,
                    requirements=action.requirements,
                    actor=agent.id,
                )
                return {"ref": ref.model_dump(mode="json")}, "active"
            case Verify():
                ref = project.evidence(action.evidence, actor=agent.id)
                return {"ref": ref.model_dump(mode="json")}, "active"
            case Deliver():
                if agent.decision_id is None:
                    raise PermissionError("Missing governing plan")
                ref = project.deliver(
                    Deliverable(
                        spec_id=action.spec_id,
                        artifacts=action.artifacts,
                        evidence=action.evidence,
                        rationale_id=rationale_id,
                    ),
                    decision_id=agent.decision_id,
                    actor=agent.id,
                )
                return {"ref": ref.model_dump(mode="json")}, "active"
            case Review():
                ref = await project.reviews.generate(
                    action.decision_id,
                    actor=agent.id,
                    run_id=self.run_id,
                    parent_id=state.request_id,
                    rationale_id=rationale_id,
                    packet_id=packet.id,
                )
                return {
                    "ref": ref.model_dump(mode="json"),
                    "review": store.resolve(ref).data,
                }, "waiting"
            case Finish():
                validated = project.tools.payload(agent.result_schema, action.result)
                if isinstance(validated, TaskReport):
                    for ref in validated.evidence:
                        store.resolve(ref, current=True)
                    if validated.unresolved:
                        return {
                            "reason": "Unresolved task work",
                            "items": list(validated.unresolved),
                        }, "waiting"
                if is_chief and not all(
                    project.reviews.accepted(stage)
                    for stage in self.request.target_reviews
                ):
                    raise ValueError("Required reviews are not human-accepted")
                obligations = [
                    e
                    for e in activity.inbox(agent.id)
                    if e.response_required
                    and e.response_message_id is None
                    and e.message.kind != "delegation"
                ]
                if obligations:
                    raise ValueError("Outstanding inbox response obligations")
                activity.transition(
                    state.request_id, "completed", actor=agent.id, result=action.result
                )
                if agent.parent_id:
                    original = next(
                        e
                        for e in activity.inbox(agent.id)
                        if e.message.kind == "delegation"
                    )
                    response = MessageEnvelope(
                        project_id=store.project_id,
                        run_id=self.run_id,
                        sender=agent.id,
                        recipient=agent.parent_id,
                        kind="reply",
                        schema_id=agent.result_schema,
                        payload=action.result,
                        request_id=state.request_id,
                        parent_request_id=activity.get(state.request_id).parent_id,
                        reply_to=original.message.id,
                        context_refs=(store.get("context", packet.id).ref,),
                    )
                    activity.deliver(response)
                    store.put(
                        "inbox",
                        original.message.id,
                        original.model_copy(
                            update={"response_message_id": response.id}
                        ),
                        actor=agent.id,
                        request_id=state.request_id,
                        event="message.answered",
                    )
                    parent = store.model("agent", agent.parent_id, AgentSpec)
                    parent_state = store.model("agent_state", parent.id, AgentState)
                    if parent_state.status == "waiting":
                        self._wake(parent, parent_state, "Worker completed")
                return {"result": action.result}, "completed"
            case Wait():
                return {"reason": action.reason}, "waiting"
        raise TypeError("Unsupported action")
