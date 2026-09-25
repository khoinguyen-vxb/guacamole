"""Validated local jobs; cancelling a wait never claims to kill a Python thread."""

import asyncio
import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..contracts import JSON, Ref, RequestRecord, ToolGrant
from .registry import Tool, encode

if TYPE_CHECKING:
    from ..project import Project


@dataclass(frozen=True)
class Job[R]:
    id: str
    _project: "Project"
    _task: asyncio.Task[R]

    @property
    def record(self) -> RequestRecord:
        return self._project.activity.get(self.id)

    async def collect(self, timeout: float | None = None) -> R:
        try:
            async with asyncio.timeout(timeout):
                return await asyncio.shield(self._task)
        except TimeoutError:
            self._project.store.event(
                "script",
                "job.wait_timed_out",
                self.id,
                {"execution_continues": True},
                request_id=self.id,
            )
            raise

    def cancel(self) -> None:
        if not self._task.done():
            self._project.activity.transition(
                self.id,
                "cancel_requested",
                actor="script",
                reason="Caller requested cancellation; running callable may still finish",
            )


class Executor:
    def __init__(self, project: "Project") -> None:
        self.project = project
        self.jobs: dict[str, Job] = {}

    def retry(
        self, request_id: str, *, actor: str, reason: str, reconciled: bool = False
    ) -> Job:
        record = self.project.activity.get(request_id)
        if record.kind != "tool" or (actor != "script" and actor != record.requester):
            raise PermissionError("Only the requester or the user can retry a tool job")
        tool = self.project.tools.get(record.target)
        if not tool.definition.retry_safe and not (actor == "script" and reconciled):
            raise ValueError(
                "Provider does not declare retries safe; reconcile the outcome explicitly"
            )
        if actor != "script" and record.status == "uncertain":
            raise PermissionError(
                "Only the user can reconcile an uncertain external outcome"
            )
        snapshot = self.project.store.get("job_inputs", record.id)
        for ref in snapshot.dependencies:
            self.project.store.resolve(ref, current=True)
        self.project.activity.retry(
            request_id, actor=actor, reason=reason, reconcile_uncertain=reconciled
        )
        return self.submit(
            tool,
            record.arguments,
            actor=record.requester,
            run_id=record.run_id,
            parent_id=record.parent_id,
            decision_id=record.decision_id,
            rationale_id=record.rationale_id,
            packet_id=record.packet_id,
            inputs=snapshot.dependencies,
            retry_id=request_id,
        )

    def submit[R](
        self,
        tool: Tool[..., R],
        arguments: JSON,
        *,
        actor: str = "script",
        grants: tuple[ToolGrant, ...] | None = None,
        run_id: str = "script",
        parent_id: str | None = None,
        decision_id: str | None = None,
        rationale_id: str | None = None,
        packet_id: str | None = None,
        inputs: tuple[Ref, ...] = (),
        retry_id: str | None = None,
    ) -> Job[R]:
        if self.project.tools.get(tool.key) is not tool:
            raise PermissionError("Tool is not registered in this project")
        if grants is not None and tool.definition.grant not in grants:
            raise PermissionError(f"Tool not granted: {tool.key}")
        if actor != "script":
            if decision_id is None:
                raise PermissionError("Agent tools require a governing Jev decision")
            self.project.decisions.plan(decision_id)
        for ref in inputs:
            self.project.store.resolve(ref, current=True)
        call_args = tool.arguments(arguments)
        if retry_id:
            record = self.project.activity.get(retry_id)
            if (
                record.status != "queued"
                or record.target != tool.key
                or record.arguments != arguments
            ):
                raise ValueError(
                    "Retry must preserve the logical request and arguments"
                )
        else:
            record = self.project.activity.request(
                RequestRecord(
                    run_id=run_id,
                    requester=actor,
                    target=tool.key,
                    kind="tool",
                    arguments=arguments,
                    purpose=tool.definition.description,
                    parent_id=parent_id,
                    decision_id=decision_id,
                    rationale_id=rationale_id,
                    packet_id=packet_id,
                )
            )
        self.project.store.put(
            "job_inputs",
            record.id,
            {"tool": tool.definition.model_dump(mode="json"), "arguments": arguments},
            actor=actor,
            dependencies=inputs,
            request_id=record.id,
        )
        # Persist all intent before scheduling. No work runs if either write fails.
        task = asyncio.create_task(self._execute(record, tool, call_args, inputs))
        job = Job(record.id, self.project, task)
        self.jobs[job.id] = job
        task.add_done_callback(
            lambda done: None if done.cancelled() else done.exception()
        )
        return job

    async def _execute[R](
        self,
        record: RequestRecord,
        tool: Tool[..., R],
        args: dict[str, object],
        inputs: tuple[Ref, ...],
    ) -> R:
        activity, store = self.project.activity, self.project.store
        if activity.expired(record.id):
            raise TimeoutError("Request deadline passed before dispatch")
        if activity.get(record.id).status == "cancel_requested":
            activity.transition(
                record.id,
                "cancelled",
                actor="runtime",
                reason="Cancelled before dispatch",
            )
            raise asyncio.CancelledError
        activity.transition(record.id, "dispatched", actor="runtime")
        activity.transition(record.id, "running", actor="runtime")
        try:
            if inspect.iscoroutinefunction(tool.function):
                raw = await tool.function(**args)
            else:
                raw = await asyncio.to_thread(tool.function, **args)
                if inspect.isawaitable(raw):
                    raw = await raw
            result = tool.result(raw)
            payload = tool.output.dump_python(result, mode="json", warnings="error")
            encode(payload)
            with store.atomic():
                self.project.capture_files(record.id, payload)
                store.put(
                    "tool_result",
                    record.id,
                    {"value": payload, "physical_acceptance": "not_assessed"},
                    actor="runtime",
                    dependencies=(*inputs, store.get("job_inputs", record.id).ref),
                    request_id=record.id,
                )
                activity.transition(
                    record.id, "completed", actor="runtime", result=payload
                )
            return result
        except asyncio.CancelledError:
            activity.transition(
                record.id,
                "uncertain",
                actor="runtime",
                reason="Runtime interrupted; external/thread execution may continue",
            )
            raise
        except Exception as exc:
            # Exception messages can contain provider credentials or arbitrary tool output.
            activity.transition(
                record.id,
                "failed",
                actor="runtime",
                reason=f"{type(exc).__name__}; exception text omitted to avoid credential leakage",
            )
            raise

    async def drain(self) -> None:
        if self.jobs:
            await asyncio.gather(
                *(j._task for j in self.jobs.values()), return_exceptions=True
            )
