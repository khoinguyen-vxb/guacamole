"""One cooperative runtime for the Chief and task-defined workers."""

import asyncio
import time
from collections.abc import Awaitable
from pathlib import Path
from types import CoroutineType
from typing import Any

from ..context import (
    IMAGE_TYPES,
    ContextOverflow,
    ProviderError,
    ReasoningProvider,
    preview,
)
from ..contracts import (
    JSON,
    TERMINAL,
    Acknowledge,
    AgentSpec,
    AgentState,
    AgentTurn,
    Amend,
    AmendmentRecord,
    AskHuman,
    Compact,
    ContextPacket,
    Decide,
    DecisionRecord,
    Deliver,
    Deliverable,
    Extract,
    Finish,
    InboxEntry,
    MessageEnvelope,
    Note,
    Omission,
    OpenItem,
    ProjectRequest,
    ProjectResult,
    Publish,
    Qualification,
    RationaleRecord,
    Read,
    Record,
    Ref,
    RequestRecord,
    Requirement,
    Retry,
    Review,
    Send,
    Spawn,
    Supersede,
    TaskAuthorization,
    TaskReport,
    ToolCall,
    UpdateModel,
    Verify,
    Wait,
    now,
    uid,
)
from ..decision import DecisionBlocked
from ..integrations.sysml.registry import ModelRejected
from ..middleware import ContextMiddleware, Invocation
from ..project import Project
from ..tools.execution import Job, ToolError
from ..tools.registry import encode
from .chief import CHIEF, COMMON
from .systems_engineer import SYSTEMS_ENGINEER

# Share of its measured trials in a family a tier must pass to be routed that work.
MIN_PASS_RATE = 0.8


class Runtime:
    def __init__(self, project: Project, provider: ReasoningProvider) -> None:
        self.project, self.provider = project, provider
        self.calls = asyncio.Semaphore(project.max_concurrent_calls)
        self.tier_menu = self._tier_menu()
        self.run_id = ""
        self.chief_id = ""
        self.engineer_id = ""
        self.request: ProjectRequest
        self.input_tokens = 0

    def _records(self, provider: ReasoningProvider) -> tuple[Qualification, ...]:
        profile = (provider.name, provider.model, getattr(provider, "effort", None))
        return tuple(
            q
            for q in self.project.qualifications
            if (q.provider, q.model, q.effort) == profile
        )

    def _route(self, task: TaskAuthorization) -> tuple[str | None, str]:
        """The task's tier: the Chief's override, else the cheapest qualified one."""
        if task.tier is not None:
            return task.tier, "Chief-selected tier"
        # Expected cost of one verified completion, retries on failure included.
        ranked = sorted(
            (q.cost_usd is None, (q.cost_usd or 0.0) / q.passed, key)
            for key, provider in self.project.tiers.items()
            for q in self._records(provider)
            if q.family == task.family and q.passed >= MIN_PASS_RATE * q.trials
        )
        if not ranked:
            return None, f"No tier qualified for family {task.family}; Chief's model"
        return ranked[0][2], f"Cheapest tier qualified for family {task.family}"

    def _tier_menu(self) -> str:
        """Fixed per run so the Chief's instruction prefix stays cacheable."""
        if not self.project.tiers:
            return ""
        lines = []
        for key, p in self.project.tiers.items():
            effort = getattr(p, "effort", None)
            lines.append(
                f"Worker reasoning tier {key}: {p.name} {p.model}"
                + (f" effort {effort}" if effort else "")
                + f", {p.context_capacity_tokens} context tokens."
            )
            for q in self._records(p):
                lines.append(
                    f"  {q.family}: {q.passed}/{q.trials} trials verified"
                    + (
                        f", ${q.cost_usd / q.passed:.3f} per verified completion"
                        if q.passed and q.cost_usd is not None
                        else ""
                    )
                    + ("" if q.passed >= MIN_PASS_RATE * q.trials else ", unqualified")
                )
        lines.append(
            "Give each task a family naming its kind of work, reusing the families "
            "above where they fit. The runtime runs it on the cheapest tier qualified "
            "for that family, or on your model when none is; set a task's tier only "
            "to override that choice."
        )
        return "\n" + "\n".join(lines)

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
        if self._awaiting_human(agent.id):
            return
        record = self.project.activity.get(state.request_id)
        if record.status == "blocked":
            self.project.activity.retry(record.id, actor="runtime", reason=reason)
        update: JSON = {"status": "active"}
        if agent.id == self.engineer_id:
            # It serves the whole run: its budget bounds each wake-to-wait episode
            # (a model that never validates), so a long run cannot wear it out.
            update |= {"steps": 0, "tool_calls": 0, "elapsed_s": 0.0}
        self._save_state(agent, state.model_copy(update=update))

    def _adopt_plan(self, chief: AgentSpec) -> None:
        """Move running workers onto the chief's current plan when it keeps their task.

        Otherwise a replacement plan (e.g. one covering a new requirement) left
        workers on the old plan, which then failed validation on every tool call.
        """
        store = self.project.store
        if chief.decision_id is None:
            return
        plan = self.project.decisions.plan(chief.decision_id)
        tasks = {t.id: t for t in plan.tasks}
        decision = store.get("decision", chief.decision_id).ref
        for worker in self._agents():
            task = tasks.get(worker.task_id)
            state = store.model("agent_state", worker.id, AgentState)
            if (
                worker.parent_id != chief.id
                or task is None
                or worker.decision_id == chief.decision_id
                or state.status in {"completed", "superseded"}
            ):
                continue
            previous_inputs = ()
            if worker.decision_id:
                previous = store.model("decision", worker.decision_id, DecisionRecord)
                previous_plan = next(
                    c.plan
                    for c in previous.request.candidates
                    if c.id == previous.result.selected
                )
                previous_inputs = previous_plan.inputs if previous_plan else ()
            pins = tuple(
                r
                for r in worker.context.pinned
                if r.kind != "decision" and r not in previous_inputs
            )
            store.put(
                "agent",
                worker.id,
                worker.model_copy(
                    update={
                        "decision_id": chief.decision_id,
                        "objective": task.objective,
                        "tools": task.tools,
                        "peers": task.peers,
                        "result_schema": task.result_schema,
                        "completion_criteria": task.completion_criteria,
                        # A replan is how the Chief escalates a running task's tier.
                        "tier": self._route(task)[0],
                        "context": worker.context.model_copy(
                            update={
                                "pinned": tuple(
                                    dict.fromkeys((*pins, *plan.inputs, decision))
                                )
                            }
                        ),
                    }
                ),
                actor="runtime",
                request_id=state.request_id,
                event="agent.plan_assigned",
            )
            if "selected" in state.observation:
                reads = Read.model_validate_json(
                    encode({"refs": state.observation["selected"]})
                )
                retained = []
                for ref in reads.refs:
                    try:
                        store.resolve(ref, current=True)
                    except ValueError:
                        store.event(
                            "runtime",
                            "agent.pending_reads_repaired",
                            worker.id,
                            {"removed": [ref.model_dump(mode="json")]},
                            request_id=state.request_id,
                        )
                        continue
                    retained.append(ref.model_dump(mode="json"))
                state = state.model_copy(
                    update={"observation": state.observation | {"selected": retained}}
                )
                self._save_state(worker, state)
            if state.status in {"blocked", "waiting"}:
                assigned = store.model("agent", worker.id, AgentSpec)
                self._wake(assigned, state, "Replacement work plan")

    def _awaiting_human(self, agent_id: str) -> bool:
        return any(
            entry.message.sender == agent_id
            and self.project.activity.get(entry.message.request_id or "").required
            for entry in self.project.human.inbox(run_id=self.run_id)
        )

    def _add_agent(
        self, agent: AgentSpec, *, parent_request: str | None, required: bool = True
    ) -> None:
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
                    required=required,
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
                data = store.get("source", ref.id).data
                # Images reach a provider as pixels when an agent reads them.
                if data.get("text") is None and data["media_type"] not in IMAGE_TYPES:
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
            engineer = self.project.systems_engineer.spec(chief, request.budget)
            self.engineer_id = engineer.id
            store.put(
                "run",
                self.run_id,
                {
                    "request": request.model_dump(mode="json"),
                    "chief_id": chief.id,
                    "engineer_id": self.engineer_id,
                    "status": "running",
                },
                actor="script",
            )
            self._add_agent(chief, parent_request=None)
            # The engineer starts the project by recording and modeling the
            # requirements; the first usable model wakes the chief (UpdateModel).
            state = store.model("agent_state", chief.id, AgentState)
            self._save_state(chief, state.model_copy(update={"status": "waiting"}))
            # It serves the whole run and never finishes: not a required request.
            self._add_agent(engineer, parent_request=None, required=False)
        else:
            if request is not None:
                raise ValueError(
                    "Resume uses the persisted request; record changes explicitly"
                )
            self.run_id = resume
            run = store.get("run", resume).data
            self.request = ProjectRequest.model_validate_json(encode(run["request"]))
            self.chief_id = str(run["chief_id"])
            self.engineer_id = str(run.get("engineer_id") or "")
            for agent in self._agents():
                state = store.model("agent_state", agent.id, AgentState)
                if state.status == "superseded":
                    continue
                if self._awaiting_human(agent.id):
                    continue
                record = self.project.activity.get(state.request_id)
                if record.status in {"interrupted", "blocked"}:
                    self.project.activity.retry(
                        record.id,
                        actor="script",
                        reason="Explicit resume of agent reasoning; tools are not replayed",
                    )
                if record.status != "completed":
                    self._wake(agent, state, "Explicit resume")
            chief = store.model("agent", self.chief_id, AgentSpec)
            if chief.decision_id:
                try:
                    self._adopt_plan(chief)
                except (ValueError, KeyError, DecisionBlocked):
                    pass  # An invalid chief plan is the chief's to replace first.
            if not self.engineer_id:  # Runs saved before the engineer was required.
                engineer = self.project.systems_engineer.spec(
                    chief, self.request.budget
                )
                self.engineer_id = engineer.id
                store.put(
                    "run", resume, {**run, "engineer_id": engineer.id}, actor="script"
                )
                self._add_agent(engineer, parent_request=None, required=False)
        if self.request.budget.max_run_input_tokens is not None:
            # A resumed run keeps counting what it already sent, failed calls included.
            ids = {r.id for r in self.project.requests() if r.run_id == self.run_id}
            self.input_tokens = sum(
                int(str(e.details["input_tokens"]))
                for e in store.events()
                if e.type == "provider.dispatched" and e.request_id in ids
            )
        start = time.monotonic()
        self.deadline = start + self.request.budget.max_seconds
        watchdog = self.project.watchdog
        supervisor = None
        if watchdog is not None:
            watchdog.start(self)
            supervisor = asyncio.create_task(watchdog.supervise())
        try:
            # Agents reason concurrently, each with at most one turn in flight.
            async with asyncio.TaskGroup() as group:
                running: dict[str, asyncio.Task[None]] = {}
                while time.monotonic() - start < self.request.budget.max_seconds:
                    for agent in self._agents():
                        state = store.model("agent_state", agent.id, AgentState)
                        if agent.id not in running and state.status == "active":
                            running[agent.id] = group.create_task(
                                self.step(agent, state)
                            )
                    if not running:
                        break
                    # ponytail: 1 s poll picks up agents woken outside a turn (human
                    # input, watchdog); an asyncio.Event set on wake would remove it.
                    done, _ = await asyncio.wait(
                        running.values(), timeout=1, return_when=asyncio.FIRST_COMPLETED
                    )
                    running = {k: t for k, t in running.items() if t not in done}
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
        finally:
            if supervisor is not None:
                supervisor.cancel()
                await asyncio.gather(supervisor, return_exceptions=True)
        if watchdog is not None:
            watchdog.report()
            watchdog.stop()
        reviews = tuple(s.ref for s in store.list("review") if not s.stale)
        accepted = all(
            self.project.reviews.accepted(stage)
            for stage in self.request.target_reviews
        )
        awaiting = any(
            store.get("review", r.id).data["status"] == "ready" for r in reviews
        )
        human_requests = self.project.human.inbox(run_id=self.run_id)
        awaiting_human = any(
            (
                record := self.project.activity.get(entry.message.request_id or "")
            ).required
            and "review" not in record.arguments
            for entry in human_requests
        )
        open_items = [
            str(s.data["description"])
            for s in store.list("open_item")
            if not s.data["resolved_by"] or s.stale
        ]
        open_items.extend(self.project.sysml.review_issues())
        for agent in self._agents():
            state = store.model("agent_state", agent.id, AgentState)
            idle = agent.id == self.engineer_id and state.status == "waiting"
            if state.status not in {"completed", "superseded"} and not idle:
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
            else "awaiting_human"
            if awaiting_human
            else "awaiting_review"
            if awaiting
            else "incomplete",
            reviews=reviews,
            human_requests=tuple(
                entry.message.request_id or "" for entry in human_requests
            ),
            open_items=tuple(open_items),
        )
        store.put(
            "run",
            self.run_id,
            {
                "request": self.request.model_dump(mode="json"),
                "chief_id": self.chief_id,
                "engineer_id": self.engineer_id,
                "status": result.status,
                "result": result.model_dump(mode="json"),
            },
            actor="runtime",
        )
        return result

    def _context_state(
        self, agent: AgentSpec, state: AgentState, pinned: tuple[Ref, ...] = ()
    ) -> JSON:
        store = self.project.store
        is_chief = agent.id == self.chief_id
        requests = [
            r for r in self.project.activity.requests() if r.run_id == self.run_id
        ]
        own = {r.id for r in requests if r.requester == agent.id}
        pins = {(r.kind, r.id, r.revision) for r in pinned}
        # last_observation holds only the latest result, so without this agents
        # re-ran reads they had made one call earlier.
        # ponytail: fixed window of 8 calls; results run to ~18k chars each, so
        # only previews repeat every turn and the full value stays one read away.
        recent = sorted(
            (
                r
                for r in requests
                if r.requester == agent.id
                and r.kind == "tool"
                and r.status in TERMINAL
                and r.id != state.observation.get("request_id")
            ),
            key=lambda r: r.created_at,
        )[-8:]
        results = {
            r.id: snapshot.ref.model_dump(mode="json")
            for r in recent
            if (snapshot := store.maybe("tool_result", r.id)) and not snapshot.stale
        }
        context: JSON = {
            "run_id": self.run_id,
            "workspace": str(store.directory),
            "sandbox": str(self.project.sandbox),
            "last_observation": state.observation,
            # Inbox context drops acknowledged mail and never shows outgoing mail, so
            # workers re-sent the same report every turn without this.
            # ponytail: last 5 sends, payloads cut at 2000 chars.
            "sent_messages": [
                {
                    "id": m.id,
                    "recipient": m.recipient,
                    "kind": m.kind,
                    "created_at": m.created_at,
                    "payload": encode(m.payload)[:2000],
                }
                for m in self.project.activity.sent(agent.id)[-5:]
            ],
            "agents": [
                {
                    "id": a.id,
                    "task_id": a.task_id,
                    "status": store.get("agent_state", a.id).data["status"],
                }
                for a in self._agents()
            ],
            # Stale records cannot be read or cited, and finished requests stay
            # reachable through their results; listing them grew every prompt.
            # So did pinned records, which arrive whole among the sources, and other
            # agents' tool records, one pair per call in the run; only the Chief,
            # which weighs everyone's results, keeps their tool_result refs.
            "records": [
                s.ref.model_dump(mode="json")
                for s in store.list(
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
                    "job_file",
                    "system_model",
                    "amendment",
                )
                if not s.stale
                and (s.ref.kind, s.ref.id, s.ref.revision) not in pins
                and (
                    s.ref.kind not in {"tool_result", "job_inputs", "job_file"}
                    or s.ref.id in own
                    or (is_chief and s.ref.kind == "tool_result")
                    # Produced images, readable as pixels; other files publish by path.
                    or (
                        s.ref.kind == "job_file"
                        and s.data["media_type"] in IMAGE_TYPES
                        and (is_chief or s.data["producer_request"] in own)
                    )
                )
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
                for r in requests
                if r.status not in {"completed", "cancelled"}
                and (is_chief or agent.id in {r.requester, r.target})
            ],
            "recent_tool_calls": [
                {
                    "request_id": r.id,
                    "tool": r.target,
                    "arguments": preview(r.arguments, 1_000),
                    "status": r.status,
                    "result": preview(r.result, 2_000),
                    "reason": r.reason,
                }
                | ({"ref": results[r.id]} if r.id in results else {})
                for r in recent
            ],
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
        if is_chief and agent.decision_id:
            # The finish line, which agents never saw: no run had tried to deliver.
            try:
                context["review_blockers"] = [
                    *self.project.reviews.checks(agent.decision_id)[2],
                    *self.project.sysml.review_issues(),
                ]
            except (ValueError, KeyError, DecisionBlocked) as exc:
                context["review_blockers"] = [f"Current work plan is unusable: {exc}"]
        context["system_model"] = self.project.sysml.state(
            engineer=agent.id == self.engineer_id
        )
        return context

    async def _hook(
        self,
        middleware: ContextMiddleware,
        hook: CoroutineType[Any, Any, None],
        request_id: str,
    ) -> None:
        try:
            await hook
        except Exception as exc:  # noqa: BLE001 -- optional middleware never stops a run
            self.project.store.event(
                "runtime",
                "middleware.failed",
                type(middleware).__name__,
                {"hook": hook.__qualname__, "error_type": type(exc).__name__},
                request_id=request_id,
            )

    async def step(self, agent: AgentSpec, state: AgentState) -> None:
        activity, store = self.project.activity, self.project.store
        agent = store.model("agent", agent.id, AgentSpec)
        human_version = self.project.human.version(self.run_id)
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
        started, since = time.monotonic(), now()
        phase = "context"
        changed = state.model_copy(update={"steps": state.steps + 1})
        self._save_state(agent, changed)
        pending_reads = (
            {"selected": state.observation["selected"]}
            if state.observation.get("selected")
            else {}
        )
        try:
            # A worker keeps its spawned tier; a tier dropped from config blocks it
            # rather than silently moving it onto another model.
            if agent.tier is None:
                provider = self.provider
            elif agent.tier in self.project.tiers:
                provider = self.project.tiers[agent.tier]
            else:
                raise ProviderError(f"Reasoning tier {agent.tier} is not configured")
            # Explicit reads must arrive next turn or block, never be silently deferred.
            requested = Read.model_validate_json(
                encode({"refs": state.observation.get("selected", [])})
            ).refs
            pins = (
                *tuple(
                    s.ref
                    for s in store.list("requirement")
                    if not s.stale and not s.data.get("withdrawn")
                ),
                *self.project.human.references(self.run_id),
                *requested,
            )
            # The full arguments of the call just made: recent_tool_calls only
            # previews them, so agents spent a turn reading them back. Selected for
            # this turn, not pinned, so an oversized one is deferred, not overflowing.
            ran = state.observation.get("ref")
            made = (
                store.maybe("job_inputs", str(ran.get("id")))
                if isinstance(ran, dict) and ran.get("kind") == "tool_result"
                else None
            )
            latest = (made.ref,) if made is not None and not made.stale else ()
            actual = agent.model_copy(
                update={
                    "context": agent.context.model_copy(
                        update={
                            "pinned": tuple(
                                dict.fromkeys((*agent.context.pinned, *pins))
                            ),
                            "selected": tuple(
                                dict.fromkeys((*latest, *agent.context.selected))
                            ),
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
                call = Invocation(
                    self.project,
                    actual,
                    query=f"{agent.objective}\n{encode(state.observation)}"[:4000],
                )
                for middleware in self.project.middleware:
                    await self._hook(
                        middleware, middleware.before_model(call), state.request_id
                    )
                # Queue before assembly so the prompt is current when it is sent;
                # the slot is released before the action runs tools.
                async with self.calls:
                    plan = (
                        store.maybe("decision", agent.decision_id)
                        if agent.id == self.chief_id and agent.decision_id
                        else None
                    )
                    if plan is not None and plan.stale:
                        # Let the Chief replace its plan; tool authorization still rejects it.
                        call.agent = call.agent.model_copy(
                            update={
                                "context": call.agent.context.model_copy(
                                    update={
                                        "pinned": tuple(
                                            r
                                            for r in call.agent.context.pinned
                                            if r != plan.ref
                                        )
                                    }
                                )
                            }
                        )
                        call.omissions.append(
                            Omission(
                                item=f"decision:{plan.ref.id}@{plan.ref.revision}",
                                reason="Work plan is stale; decide a replacement before continuing work",
                            )
                        )
                    context_state = self._context_state(
                        agent, state, call.agent.context.pinned
                    )

                    def build(spec: AgentSpec) -> Awaitable[ContextPacket]:
                        return self.project.contexts.build(
                            spec,
                            state.request_id,
                            provider,
                            instructions=CHIEF + self.tier_menu
                            if agent.id == self.chief_id
                            else SYSTEMS_ENGINEER
                            if agent.id == self.engineer_id
                            else COMMON,
                            state=context_state,
                            memory=call.memory,
                            omissions=call.omissions,
                            catalogue=agent.id == self.chief_id,
                        )

                    try:
                        packet = await build(call.agent)
                    except ContextOverflow:
                        # Budgets are set without seeing the runtime state each prompt
                        # carries; required material may grow them to the run's limit.
                        limit = min(
                            self.request.context.max_input_tokens,
                            provider.context_capacity_tokens
                            - call.agent.context.reserved_output_tokens,
                        )
                        previous = call.agent.context.max_input_tokens
                        if previous >= limit:
                            raise
                        stored = store.model("agent", agent.id, AgentSpec)
                        with store.atomic():
                            store.put(
                                "agent",
                                agent.id,
                                stored.model_copy(
                                    update={
                                        "context": stored.context.model_copy(
                                            update={"max_input_tokens": limit}
                                        )
                                    }
                                ),
                                actor="runtime",
                                request_id=state.request_id,
                            )
                            store.event(
                                "runtime",
                                "agent.budget_raised",
                                agent.id,
                                {"from": previous, "to": limit},
                                request_id=state.request_id,
                            )
                        call.agent = call.agent.model_copy(
                            update={
                                "context": call.agent.context.model_copy(
                                    update={"max_input_tokens": limit}
                                )
                            }
                        )
                        packet = await build(call.agent)
                    if self.project.human.version(self.run_id) != human_version:
                        return
                    cap = self.request.budget.max_run_input_tokens
                    if (
                        cap is not None
                        and self.input_tokens + packet.input_tokens > cap
                    ):
                        raise ProviderError(
                            f"Run input-token budget exhausted: {self.input_tokens:,} "
                            f"of {cap:,} estimated tokens sent; raise "
                            "max_run_input_tokens to continue"
                        )
                    # Counted here, before any await, so concurrent turns cannot overshoot.
                    self.input_tokens += packet.input_tokens
                    store.event(
                        agent.id,
                        "provider.dispatched",
                        packet.invocation_id,
                        {
                            "packet_id": packet.id,
                            "provider": provider.name,
                            "model": provider.model,
                            "tier": agent.tier,
                            "effort": getattr(provider, "effort", None),
                            "input_tokens": packet.input_tokens,
                            "max_input_tokens": call.agent.context.max_input_tokens,
                            "deferred": len(packet.deferred),
                            "images": len(packet.images),
                            "components": {**packet.components},
                        },
                        request_id=state.request_id,
                    )
                    phase = "provider"
                    turn = AgentTurn.model_validate(await provider.respond(packet))
                store.put(
                    "agent_turn",
                    packet.invocation_id,
                    turn,
                    actor=agent.id,
                    dependencies=(store.get("context", packet.id).ref,),
                    request_id=state.request_id,
                    event="provider.responded",
                    allow_stale_dependencies=True,
                )
                if self.project.human.version(self.run_id) != human_version:
                    store.event(
                        "runtime",
                        "agent.turn_superseded",
                        packet.invocation_id,
                        {"reason": "Human input arrived during this invocation"},
                        request_id=state.request_id,
                    )
                    return
                # A replan can move a worker to another plan, tools or tier mid-call;
                # its reply answered the old one, so reason again instead of acting.
                if store.model("agent", agent.id, AgentSpec).decision_id != (
                    agent.decision_id
                ):
                    store.event(
                        "runtime",
                        "agent.turn_superseded",
                        packet.invocation_id,
                        {"reason": "The agent's plan changed during this invocation"},
                        request_id=state.request_id,
                    )
                    return
                phase = "rationale"
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
                if self.project.human.version(self.run_id) != human_version:
                    return
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
            # ponytail: memory ingestion is inline and untimed; background it if slow.
            for middleware in self.project.middleware:
                await self._hook(
                    middleware,
                    middleware.after_model(call, turn, observation),
                    state.request_id,
                )
        except TimeoutError:
            if self.project.human.version(self.run_id) != human_version:
                return
            reason = "Invocation timed out; dispatched tools may still be running"
            changed = changed.model_copy(
                update={
                    "status": "blocked",
                    "observation": pending_reads | {"reason": reason},
                }
            )
            activity.transition(
                state.request_id, "blocked", actor="runtime", reason=reason
            )
        except ContextOverflow as exc:
            if self.project.human.version(self.run_id) != human_version:
                return
            changed = changed.model_copy(
                update={
                    "status": "blocked",
                    "observation": pending_reads
                    | {"reason": str(exc) or type(exc).__name__},
                }
            )
            activity.transition(
                state.request_id,
                "blocked",
                actor="runtime",
                reason=str(exc) or type(exc).__name__,
            )
        except Exception as exc:  # noqa: BLE001 -- persist provider/tool failures for correction
            if self.project.human.version(self.run_id) != human_version:
                return
            invalid_rationale = phase == "rationale" and isinstance(exc, ValueError)
            invalid_read = (
                phase == "action"
                and isinstance(turn.action, Read)
                and isinstance(exc, ValueError)
            )
            # The runtime wrote these messages; tool exceptions may carry secrets.
            # A rejected decision stays correctable: blocking the Chief ended the run.
            runtime_rejection = (
                phase == "action"
                and not isinstance(turn.action, (ToolCall, Retry))
                and isinstance(
                    exc, (ValueError, KeyError, PermissionError, DecisionBlocked)
                )
            )
            detail = (
                "Read contains an unknown, mismatched, or stale reference. "
                "Copy exact current Ref objects from the context and retry; no read queued."
                if invalid_read
                else "Rationale evidence contains an unknown, mismatched, or stale reference. "
                "Copy exact current Ref objects from the context and retry; no action executed."
                if invalid_rationale
                else f"Action rejected: {exc}"[:1000]
                if runtime_rejection
                else (
                    str(exc)
                    if isinstance(exc, ProviderError)
                    and phase in {"context", "provider"}
                    or isinstance(exc, ToolError)
                    else "Action rejected; inspect request records. Exception text omitted."
                )
            )
            # The next turn can correct a rejected proposal; failed tool work stays visible.
            changed = changed.model_copy(
                update={
                    "observation": pending_reads
                    | {
                        "error_type": type(exc).__name__,
                        "phase": phase,
                        "detail": detail,
                    }
                    # Every issue of a rejected model, beyond the detail's length cap.
                    | (
                        {"report": exc.report.model_dump(mode="json")}
                        if isinstance(exc, ModelRejected)
                        else {}
                    )
                }
            )
            if phase != "action" and not invalid_rationale:
                changed = changed.model_copy(update={"status": "blocked"})
                activity.transition(
                    state.request_id,
                    "blocked",
                    actor="runtime",
                    reason=f"{phase} failed: {type(exc).__name__}; {detail}",
                )
            store.event(
                "runtime",
                "action.rejected",
                agent.id,
                changed.observation,
                request_id=state.request_id,
            )
        finally:
            if self.project.human.version(self.run_id) != human_version:
                # Human input already replaced/superseded this agent's request and context.
                changed = store.model("agent_state", agent.id, AgentState)
                state = changed
            changed = changed.model_copy(
                update={"elapsed_s": state.elapsed_s + time.monotonic() - started}
            )
            current = store.model("agent", agent.id, AgentSpec)
            reassigned = (
                changed.status == "blocked" and current.decision_id != agent.decision_id
            )
            if reassigned:
                assigned = store.model("agent_state", agent.id, AgentState)
                changed = changed.model_copy(
                    update={
                        "observation": changed.observation
                        | {"selected": assigned.observation.get("selected", [])}
                    }
                )
            self._save_state(agent, changed)
            if reassigned:
                self._wake(
                    current, changed, "Replacement work plan arrived during turn"
                )
            # Senders only wake agents already waiting; catch messages sent mid-turn.
            if changed.status == "waiting" and any(
                e.delivered_at and e.delivered_at >= since
                for e in activity.inbox(agent.id)
            ):
                self._wake(agent, changed, "Message arrived during its turn")

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
        is_engineer = agent.id == self.engineer_id
        if isinstance(action, (Decide, Spawn, Review)) and not is_chief:
            raise PermissionError("Only the Chief has this operation")
        if isinstance(action, Record) and not (
            is_engineer
            if isinstance(action.record, Requirement)
            else is_chief or is_engineer
        ):
            raise PermissionError(
                "Only the systems engineer records requirements; send it the change "
                "and its source"
                if isinstance(action.record, Requirement)
                else "Only the Chief and the systems engineer record open items"
            )
        if isinstance(action, (UpdateModel, Amend)) and not is_engineer:
            raise PermissionError("Only the systems engineer changes the SysML model")
        if isinstance(action, Finish) and is_engineer:
            raise PermissionError("The systems engineer serves the whole run; use wait")
        match action:
            case AskHuman():
                request_id = project.human.ask(
                    action,
                    run_id=self.run_id,
                    sender=agent.id,
                    parent_id=state.request_id,
                    decision_id=agent.decision_id,
                    packet_id=packet.id,
                    rationale_id=rationale_id,
                )
                return {
                    "request_id": request_id,
                    "reason": action.question,
                }, "waiting" if action.blocking else "active"
            case Retry():
                try:
                    if state.tool_calls > agent.budget.max_tool_calls:
                        raise PermissionError("Tool budget exhausted")
                    job = project.executor.retry(
                        action.request_id, actor=agent.id, reason=action.reason
                    )
                except (KeyError, ValueError, PermissionError) as exc:
                    raise _refused(exc) from exc
                await _ran(job)
                return {"request_id": job.id, "result": job.record.result}, "active"
            case Supersede():
                record = activity.supersede(
                    action.request_id,
                    by=action.by,
                    actor=agent.id,
                    reason=action.reason,
                )
                return {"request_id": record.id, "reason": record.reason}, "active"
            case ToolCall():
                try:
                    if state.tool_calls > agent.budget.max_tool_calls:
                        raise PermissionError("Tool budget exhausted")
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
                except (KeyError, ValueError, PermissionError) as exc:
                    raise _refused(exc) from exc
                await _ran(job)
                return {
                    "request_id": job.id,
                    "result": job.record.result,
                    "ref": store.get("tool_result", job.id).ref.model_dump(mode="json"),
                }, "active"
            case Decide():
                plan = next(
                    (
                        c.plan
                        for c in action.request.candidates
                        if c.id == action.selected
                    ),
                    None,
                )
                # The Chief working alone kept parallel workers idle (ehopper: 61% of
                # turns, every plan granting it every tool), so it plans and reads.
                doers = [
                    grant.key
                    for grant in (plan.chief_tools if plan else ())
                    if project.tools.get(grant).definition.requires_plan
                ]
                if doers:
                    raise ValueError(
                        f"Grant {', '.join(doers)} to worker tasks, not chief_tools: "
                        "the Chief keeps reader tools (requires_plan=false) so work "
                        "runs in parallel workers"
                    )
                decision = await project.decisions.choose(
                    action.request,
                    selected=action.selected,
                    explanation=turn.rationale.explanation,
                    actor=agent.id,
                    run_id=self.run_id,
                    parent_id=state.request_id,
                    rationale_id=rationale_id,
                    packet_id=packet.id,
                )
                if action.request.kind == "work_plan":
                    plan = project.decisions.plan(decision)
                    # Reload: this turn may have raised the budget or compacted context.
                    current = store.model("agent", agent.id, AgentSpec)
                    pins = tuple(
                        r for r in current.context.pinned if r.kind != "decision"
                    )
                    updated = current.model_copy(
                        update={
                            "decision_id": decision,
                            "tools": plan.chief_tools,
                            "context": current.context.model_copy(
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
                    self._adopt_plan(updated)
                return {
                    "decision_id": decision,
                    "ref": store.get("decision", decision).ref.model_dump(mode="json"),
                }, "active"
            case Spawn():
                plan = project.decisions.plan(action.decision_id)
                task = next(t for t in plan.tasks if t.id == action.task_id)
                agents = self._agents()
                if (
                    sum(
                        a.parent_id is not None
                        and store.model("agent_state", a.id, AgentState).status
                        not in {"completed", "superseded"}
                        for a in agents
                    )
                    >= self.request.budget.max_agents
                ):
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
                tier, reason = self._route(task)
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
                    tier=tier,
                )
                self._add_agent(worker, parent_request=state.request_id)
                routed = {"family": task.family, "tier": tier, "reason": reason}
                store.event(
                    "runtime",
                    "agent.routed",
                    worker.id,
                    routed,
                    request_id=state.request_id,
                )
                return {"agent_id": worker.id, **routed}, "active"
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
                    # A reply to a reply is a follow-up; the request it shares is
                    # already closed, and closing it again rejected the send.
                    if parent_message and request_id and parent_message.kind != "reply":
                        pending = activity.get(request_id)
                        if pending.kind != "peer":
                            raise ValueError(
                                "Your task assignment cannot be replied to. Send "
                                "progress to your parent as a new message without "
                                "reply_to; use finish only when the task is complete"
                            )
                        # A request already ended (e.g. interrupted by an older
                        # restart) keeps its status; the answer is still delivered.
                        if pending.status not in TERMINAL:
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
                    if parent_message:
                        # A reply shows the message was seen. Left unacknowledged, it
                        # stayed in context looking unanswered and agents replied again.
                        activity.acknowledge(agent.id, parent_message.id)
                peer = store.model("agent_state", action.recipient, AgentState)
                if peer.status == "waiting":
                    recipient = store.model("agent", action.recipient, AgentSpec)
                    self._wake(recipient, peer, "Incoming peer message")
                return {"message_id": message.id, "request_id": request_id}, "active"
            case Acknowledge():
                with store.atomic():
                    for message_id in action.message_ids:
                        activity.acknowledge(agent.id, message_id)
                return {"acknowledged": list(action.message_ids)}, "active"
            case Record():
                if isinstance(action.record, Requirement):
                    ref = project.record_requirement(action.record, actor=agent.id)
                else:
                    ref = project.record_open_item(action.record, actor=agent.id)
                return {"ref": ref.model_dump(mode="json")}, "active"
            case Read():
                found = project.contexts.search(action.search)
                refs = (*action.refs, *found)
                for ref in refs:
                    store.resolve(ref, current=True)
                # Reload: the Chief may reassign this worker's plan while it reasons.
                current = store.model("agent", agent.id, AgentSpec)
                # Keep recent reads ahead of older optional material on later turns too.
                context = current.context.model_copy(
                    update={
                        "selected": tuple(
                            dict.fromkeys((*refs, *current.context.selected))
                        )
                    }
                )
                store.put(
                    "agent",
                    agent.id,
                    current.model_copy(update={"context": context}),
                    actor="runtime",
                )
                observation: JSON = {
                    "selected": [r.model_dump(mode="json") for r in refs]
                }
                if action.search and not found:
                    observation["search"] = (
                        "Nothing matched. Search covers current sources, artifacts, "
                        "requirements, evidence and summaries, not requests or messages."
                    )
                return observation, "active"
            case Compact():
                ref = project.compact(agent.id, action.summary, actor=agent.id)
                return {"summary": ref.model_dump(mode="json")}, "active"
            case Extract():
                ref = project.extract(action.tool_request, actor=agent.id)
                return {"ref": ref.model_dump(mode="json")}, "active"
            case Publish():
                if agent.decision_id is None:
                    raise PermissionError("Missing governing plan")
                # One turn per tool run, not per file; all of them or none.
                with store.atomic():
                    refs = [
                        project.publish(
                            path=file.path,
                            artifact_id=file.artifact_id,
                            kind=file.artifact_kind,
                            request_id=action.tool_request,
                            decision_id=agent.decision_id,
                            inputs=action.inputs,
                            requirements=action.requirements,
                            actor=agent.id,
                        )
                        for file in action.files
                    ]
                return {"refs": [r.model_dump(mode="json") for r in refs]}, "active"
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
                            "reason": "Unresolved task work; report items owned by "
                            "the parent or other tasks as handoffs instead",
                            "items": list(validated.unresolved),
                        }, "waiting"
                if is_chief and not all(
                    project.reviews.accepted(stage)
                    for stage in self.request.target_reviews
                ):
                    raise ValueError("Required reviews are not human-accepted")
                if obligations := activity.obligations(agent.id):
                    raise ValueError(
                        "Outstanding inbox response obligations; reply to "
                        + ", ".join(e.message.id for e in obligations)
                    )
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
            case UpdateModel():
                usable = self._model_usable()
                ref, invalidated = await project.sysml.commit(
                    summary=action.summary,
                    files=action.files,
                    remove=action.remove,
                    derived_from=action.derived_from,
                    implements=action.implements,
                    actor=agent.id,
                )
                members = {a.id for a in self._agents()}
                for decision_id, reason in invalidated.items():
                    author = store.model("decision", decision_id, DecisionRecord).author
                    if author in members:
                        self._note(
                            agent,
                            author,
                            f"Decision {decision_id} is stale. {reason}. Decide again "
                            "within the model's bounds.",
                            (ref,),
                        )
                if not usable and self._model_usable():
                    self._wake_waiting(self.chief_id, "SysML model is usable")
                return {
                    "ref": ref.model_dump(mode="json"),
                    "invalidated_decisions": [*invalidated],
                }, "active"
            case Amend():
                ref = await project.sysml.amend(action.amendment, actor=agent.id)
                record = store.model("amendment", ref.id, AmendmentRecord)
                status, _ = project.sysml.status(ref.id)
                if status == "withdrawal":
                    withdrawn = ", ".join(record.amendment.supersedes)
                    text = f"Amendment {ref.id} withdraws {withdrawn}."
                else:
                    changes = record.changes.requirements or record.changes.files
                    text = (
                        f"Amendment {ref.id} proposed: {record.amendment.title}. "
                        f"Changes: {'; '.join(changes)}. "
                        + (
                            ""
                            if record.report.valid
                            else "It changes requirements, so their records must "
                            "change first. "
                        )
                        + "A decide whose selected candidate cites this amendment in "
                        "its evidence adopts it; selecting another candidate of that "
                        "decision rejects it."
                    )
                self._note(agent, self.chief_id, text, (ref,))
                return {
                    "ref": ref.model_dump(mode="json"),
                    "status": status,
                    "report": record.report.model_dump(mode="json"),
                    "changes": record.changes.model_dump(mode="json"),
                }, "active"
        raise TypeError("Unsupported action")

    def _model_usable(self) -> bool:
        try:
            self.project.sysml.gate()
        except DecisionBlocked:
            return False
        return True

    def _wake_waiting(self, agent_id: str, reason: str) -> None:
        if not agent_id:
            return
        state = self.project.store.model("agent_state", agent_id, AgentState)
        if state.status == "waiting":
            agent = self.project.store.model("agent", agent_id, AgentSpec)
            self._wake(agent, state, reason)

    def _note(
        self, sender: AgentSpec, recipient: str, text: str, evidence: tuple[Ref, ...]
    ) -> None:
        """Deliver a runtime-composed finding from sender and wake its recipient."""
        store = self.project.store
        self.project.activity.deliver(
            MessageEnvelope(
                project_id=store.project_id,
                run_id=self.run_id,
                sender=sender.id,
                recipient=recipient,
                kind="finding",
                schema_id="Note@1",
                payload=Note(text=text, evidence=evidence).model_dump(mode="json"),
                parent_request_id=store.model(
                    "agent_state", sender.id, AgentState
                ).request_id,
            )
        )
        self._wake_waiting(recipient, f"Finding from {sender.task_id}")


def _refused(exc: Exception) -> ToolError:
    """A tool call the runtime refused before running it, in the runtime's own words."""
    return ToolError(f"Not run: {type(exc).__name__}: {exc}"[:2000])


async def _ran(job: Job) -> None:
    """Wait for a tool; a failure shows only what its request record kept."""
    try:
        await job.collect()
    except Exception as exc:
        raise ToolError(f"Failed: {job.record.reason or type(exc).__name__}") from exc
