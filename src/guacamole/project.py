"""Scripting interface, local artifacts, revisions, and workflow entry point."""

import fcntl
import hashlib
import mimetypes
from contextlib import ExitStack
from pathlib import Path
from typing import TYPE_CHECKING, Self

from .activity import Activity
from .context import ContextBuilder, ReasoningProvider
from .contracts import (
    JSON,
    ActivityEvent,
    ArtifactRecord,
    ContextPacket,
    Deliverable,
    Evidence,
    FileRecord,
    InboxEntry,
    MessageEnvelope,
    Note,
    OpenItem,
    ProducedFile,
    ProjectRequest,
    ProjectResult,
    Ref,
    RequestRecord,
    Requirement,
    SourceExcerpt,
    Status,
    Summary,
    TaskReport,
    VerificationResult,
    uid,
)
from .decision import Decisions, JevProvider
from .reviews import Reviews
from .storage import Store
from .tools.execution import Executor, Job
from .tools.registry import Tool, ToolRegistry, encode

if TYPE_CHECKING:
    from .agents.runtime import Runtime


class Project:
    def __init__(
        self,
        workspace: Path,
        *,
        sandbox: Path | None = None,
        tools: ToolRegistry | None = None,
        reasoning: ReasoningProvider | None = None,
        jev: JevProvider | None = None,
        read_only: bool = False,
    ) -> None:
        workspace = workspace.expanduser().resolve()
        self._lock = None
        with ExitStack() as cleanup:
            if not read_only:
                workspace.mkdir(parents=True, exist_ok=True)
                self._lock = cleanup.enter_context(
                    (workspace / "runtime.lock").open("a")
                )
                try:
                    fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise RuntimeError(
                        "This workspace already has a running Project"
                    ) from None
            self.store = Store(workspace, read_only=read_only)
            cleanup.callback(self.store.close)
            saved = self.store.db.execute(
                "SELECT value FROM metadata WHERE key='sandbox'"
            ).fetchone()
            requested = sandbox.expanduser().resolve() if sandbox is not None else None
            self._sandbox = Path(saved[0]) if saved else requested or workspace
            if saved and requested is not None and requested != self._sandbox:
                raise ValueError(f"Project already uses sandbox {self._sandbox}")
            if (
                not saved
                and self._sandbox != workspace
                and (
                    read_only
                    or self.store.db.execute("SELECT 1 FROM records LIMIT 1").fetchone()
                )
            ):
                raise ValueError(
                    "Existing project uses its workspace as sandbox; moving stored files is required"
                )
            if not read_only:
                self._sandbox.mkdir(parents=True, exist_ok=True)
                self.store.db.execute(
                    "INSERT OR IGNORE INTO metadata VALUES ('sandbox',?)",
                    (str(self._sandbox),),
                )
            self.tools = tools if tools is not None else ToolRegistry()
            for name, annotation in (("TaskReport@1", TaskReport), ("Note@1", Note)):
                if name not in self.tools.schemas:
                    self.tools.schema(name, annotation)
            self.reasoning = reasoning
            self.activity = Activity(self.store, self.tools)
            self.contexts = ContextBuilder(self.store, self.activity, self.tools)
            self.decisions = Decisions(self, jev)
            self.reviews = Reviews(self)
            self.executor = Executor(self)
            self.runtime: Runtime | None = None
            if not read_only:
                self.activity.recover()
            cleanup.pop_all()

    @property
    def sandbox(self) -> Path:
        """Shared agent output directory, persisted with the project."""
        return self._sandbox

    def output_path(self, path: Path) -> Path:
        """Resolve an output inside the sandbox, rejecting traversal and symlink escapes."""
        resolved = (self.sandbox / path).resolve()
        if not resolved.is_relative_to(self.sandbox):
            raise ValueError("Output path escapes project sandbox")
        return resolved

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if any(not j._task.done() for j in self.executor.jobs.values()):
            raise RuntimeError("Await project.drain() before closing running tools")
        self.store.close()
        if self._lock is not None:
            self._lock.close()

    async def drain(self) -> None:
        await self.executor.drain()

    def submit[R](
        self, tool: Tool[..., R], arguments: JSON, *, inputs: tuple[Ref, ...] = ()
    ) -> Job[R]:
        return self.executor.submit(tool, arguments, inputs=inputs)

    async def call[R](
        self, tool: Tool[..., R], arguments: JSON, *, inputs: tuple[Ref, ...] = ()
    ) -> R:
        return await self.submit(tool, arguments, inputs=inputs).collect()

    def retry_job(
        self, request_id: str, *, reason: str, reconciled: bool = False
    ) -> Job:
        """Explicit script retry. Unknown outcomes require a recorded reconciliation."""
        return self.executor.retry(
            request_id, actor="script", reason=reason, reconciled=reconciled
        )

    def _file(
        self,
        path: Path,
        *,
        producer: str | None = None,
        metadata: JSON | None = None,
        missing_metadata: tuple[str, ...] = (),
    ) -> FileRecord:
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        directory = self.output_path(Path("artifacts") / digest)
        directory.mkdir(parents=True, exist_ok=True)
        target = self.output_path(directory / path.name)
        if not target.exists():
            temporary = directory / f".{uid()}.tmp"
            temporary.write_bytes(data)
            temporary.replace(target)
        media = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        text = None
        # ponytail: bounded UTF-8 intake; use supplied readers for large/native formats.
        if len(data) <= 256_000 and (
            media.startswith("text/")
            or path.suffix in {".json", ".toml", ".py", ".md", ".yaml", ".yml", ".csv"}
        ):
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                pass
        missing = missing_metadata + (() if text is not None else ("reader_output",))
        if path.suffix.lower() in {".csv", ".parquet"}:
            missing += tuple(
                key
                for key in (
                    "units",
                    "frames",
                    "calibration",
                    "uncertainty",
                    "test_conditions",
                    "processing_history",
                )
                if key not in (metadata or {})
            )
        return FileRecord(
            name=path.name,
            path=str(target.relative_to(self.sandbox)),
            sha256=digest,
            media_type=media,
            origin=str(path.resolve()),
            text=text,
            metadata=metadata or {},
            missing_metadata=missing,
            producer_request=producer,
        )

    def verify_file(self, file: FileRecord) -> Path:
        path = self.output_path(Path(file.path))
        if not path.is_relative_to(self.sandbox / "artifacts"):
            raise ValueError("Artifact path escapes project storage")
        if hashlib.sha256(path.read_bytes()).hexdigest() != file.sha256:
            raise ValueError("Artifact content hash changed")
        return path

    def ingest(
        self,
        path: Path,
        *,
        source_id: str | None = None,
        metadata: JSON | None = None,
        missing_metadata: tuple[str, ...] = (),
    ) -> Ref:
        file = self._file(path, metadata=metadata, missing_metadata=missing_metadata)
        return self.store.put("source", source_id or uid(), file, actor="script")

    def capture_files(self, request_id: str, payload: object) -> None:
        if isinstance(payload, dict):
            if payload.get("kind") == "produced_file":
                output = ProducedFile.model_validate(payload)
                path = self.output_path(Path(output.path))
                file = self._file(path, producer=request_id)
                if file.sha256 != output.sha256:
                    raise ValueError(
                        "Tool output changed before it could be snapshotted"
                    )
                self.store.put(
                    "job_file",
                    f"{request_id}:{file.sha256}",
                    file,
                    actor="runtime",
                    request_id=request_id,
                )
            else:
                for value in payload.values():
                    self.capture_files(request_id, value)
        elif isinstance(payload, list):
            for value in payload:
                self.capture_files(request_id, value)

    def record_requirement(
        self, requirement: Requirement, *, actor: str = "script"
    ) -> Ref:
        source = self.store.resolve(requirement.source, current=True)
        text = source.data.get("text")
        if (
            requirement.source.kind != "source"
            or not isinstance(text, str)
            or not requirement.source_quote
            or requirement.source_quote not in text
        ):
            raise ValueError(
                "Requirement quotation must be present in its cited source"
            )
        return self.store.put(
            "requirement",
            requirement.id,
            requirement,
            actor=actor,
            dependencies=(requirement.source,),
        )

    def record_open_item(self, item: OpenItem, *, actor: str = "script") -> Ref:
        return self.store.put(
            "open_item", item.id, item, actor=actor, dependencies=item.resolved_by
        )

    def extract(self, request_id: str, *, actor: str) -> Ref:
        request = self.activity.get(request_id)
        if request.status != "completed" or request.kind != "tool":
            raise ValueError("Reader has no completed result")
        excerpt = SourceExcerpt.model_validate_json(encode(request.result))
        if excerpt.source not in self.store.get("job_inputs", request_id).dependencies:
            raise ValueError("Reader result must cite an actual input revision")
        return self.store.put(
            "source",
            uid(),
            excerpt,
            actor=actor,
            dependencies=(
                excerpt.source,
                self.store.get("tool_result", request_id).ref,
            ),
            request_id=request_id,
        )

    def summarize(self, summary: Summary, *, actor: str) -> Ref:
        return self.store.put(
            "summary", uid(), summary, actor=actor, dependencies=summary.sources
        )

    def publish(
        self,
        *,
        path: str,
        artifact_id: str,
        kind: str,
        request_id: str,
        decision_id: str,
        inputs: tuple[Ref, ...],
        requirements: tuple[Ref, ...],
        actor: str = "script",
    ) -> Ref:
        request = self.activity.get(request_id)
        self.decisions.plan(decision_id)
        if (
            request.status != "completed"
            or request.kind != "tool"
            or request.decision_id != decision_id
        ):
            raise ValueError("Artifact needs a successful tool run under this plan")
        files = [
            FileRecord.model_validate_json(encode(s.data))
            for s in self.store.list("job_file")
            if s.data.get("producer_request") == request_id
            and s.data["origin"] == str(self.output_path(Path(path)))
        ]
        if len(files) != 1:
            raise ValueError("Tool must return this path as a ProducedFile")
        self.verify_file(files[0])
        if any(r.kind != "requirement" for r in requirements):
            raise ValueError("Artifact requirement references must cite requirements")
        artifact = ArtifactRecord(
            file=files[0],
            kind=kind,
            requirements=requirements,
            inputs=inputs,
            decision_id=decision_id,
        )
        dependencies = (
            *inputs,
            *requirements,
            self.store.get("decision", decision_id).ref,
            self.store.get("tool_result", request_id).ref,
        )
        return self.store.put(
            "artifact",
            artifact_id,
            artifact,
            actor=actor,
            dependencies=dependencies,
            request_id=request_id,
        )

    def evidence(self, evidence: Evidence, *, actor: str = "script") -> Ref:
        request = self.activity.get(evidence.request_id)
        self.decisions.plan(evidence.decision_id)
        if request.status != "completed" or request.decision_id != evidence.decision_id:
            raise ValueError(
                "Evidence requires a completed tool request under its plan"
            )
        verification = VerificationResult.model_validate_json(encode(request.result))
        inputs = self.store.get("job_inputs", request.id).dependencies
        if any(ref not in inputs for ref in evidence.artifacts):
            raise ValueError(
                "Verification must actually depend on every claimed artifact revision"
            )
        if any(ref.kind != "artifact" for ref in evidence.artifacts) or any(
            ref.kind != "requirement" for ref in evidence.requirements
        ):
            raise ValueError("Evidence references have incorrect record types")
        if (
            evidence.outcome != verification.outcome
            or evidence.explanation != verification.explanation
        ):
            raise ValueError("Evidence must preserve the actual verification result")
        dependencies = (
            *evidence.artifacts,
            *evidence.requirements,
            self.store.get("tool_result", request.id).ref,
            self.store.get("decision", evidence.decision_id).ref,
        )
        return self.store.put(
            "evidence",
            evidence.id,
            evidence,
            actor=actor,
            dependencies=dependencies,
            request_id=request.id,
        )

    def deliver(
        self, deliverable: Deliverable, *, decision_id: str, actor: str = "script"
    ) -> Ref:
        plan = self.decisions.plan(decision_id)
        if deliverable.spec_id not in {d.id for d in plan.deliverables}:
            raise ValueError("Deliverable is not in the approved plan")
        self.store.get("rationale", deliverable.rationale_id)
        if any(r.kind != "artifact" for r in deliverable.artifacts) or any(
            r.kind != "evidence" for r in deliverable.evidence
        ):
            raise ValueError("Deliverable references have incorrect record types")
        return self.store.put(
            "deliverable",
            deliverable.spec_id,
            deliverable,
            actor=actor,
            dependencies=(
                *deliverable.artifacts,
                *deliverable.evidence,
                self.store.get("decision", decision_id).ref,
            ),
        )

    async def run(
        self, request: ProjectRequest | None = None, *, resume: str | None = None
    ) -> ProjectResult:
        from .agents.runtime import Runtime

        if self.reasoning is None or self.decisions.provider is None:
            missing = "reasoning" if self.reasoning is None else "Jev"
            self.store.event(
                "runtime",
                "run.blocked",
                resume or "intake",
                {"reason": f"Missing mandatory {missing} provider"},
            )
            raise RuntimeError(
                f"Configure the mandatory {missing} provider before autonomous work"
            )
        if self.runtime is not None:
            raise RuntimeError("A project run is already active")
        self.runtime = Runtime(self, self.reasoning)
        try:
            return await self.runtime.run(request, resume=resume)
        finally:
            self.runtime = None

    def inbox(self, agent_id: str) -> tuple[InboxEntry, ...]:
        return self.activity.inbox(agent_id)

    def sent(self, agent_id: str) -> tuple[MessageEnvelope, ...]:
        return self.activity.sent(agent_id)

    def requests(
        self,
        *,
        status: Status | None = None,
        agent: str | None = None,
        decision: str | None = None,
    ) -> tuple[RequestRecord, ...]:
        return self.activity.requests(status=status, agent=agent, decision=decision)

    def trace(self, request_id: str) -> JSON:
        return self.activity.trace(request_id)

    def context(self, packet_id: str) -> ContextPacket:
        return self.store.model("context", packet_id, ContextPacket)

    def events(
        self,
        after: int = 0,
        *,
        actor: str | None = None,
        request_id: str | None = None,
        since: str | None = None,
        until: str | None = None,
        decision: str | None = None,
        task: str | None = None,
    ) -> tuple[ActivityEvent, ...]:
        events = self.store.events(
            after, actor=actor, request_id=request_id, since=since
        )
        selected = self.requests(decision=decision)
        if task is not None:
            agent_ids = {
                s.ref.id for s in self.store.list("agent") if s.data["task_id"] == task
            }
            selected = tuple(
                r for r in selected if r.requester in agent_ids or r.target in agent_ids
            )
        request_ids = {r.id for r in selected}
        return tuple(
            e
            for e in events
            if (until is None or e.timestamp <= until)
            and (
                decision is None
                and task is None
                or e.request_id in request_ids
                or e.entity_id == decision
            )
        )

    def export(self, path: Path, *, readable: bool = False) -> None:
        events = self.events()
        lines = [
            f"{e.sequence} {e.timestamp} {e.actor} {e.type} {e.entity_id} {encode(e.details)}"
            if readable
            else e.model_dump_json()
            for e in events
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
