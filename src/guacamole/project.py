"""Scripting interface, local artifacts, revisions, and workflow entry point."""

import copy
import fcntl
import hashlib
import mimetypes
import re
from collections.abc import Sequence
from contextlib import ExitStack
from pathlib import Path
from typing import TYPE_CHECKING, Self

from pydantic import TypeAdapter

from .activity import Activity
from .agents.systems_engineer import SystemsEngineer
from .context import ContextBuilder, ReasoningProvider
from .contracts import (
    JSON,
    ActivityEvent,
    AgentSpec,
    ArtifactRecord,
    AskHuman,
    Catalogue,
    ContextPacket,
    Deliverable,
    Evidence,
    FileRecord,
    InboxEntry,
    LibraryPin,
    MessageEnvelope,
    Note,
    OpenItem,
    ProducedFile,
    ProjectRequest,
    ProjectResult,
    Qualification,
    Ref,
    RequestRecord,
    Requirement,
    Scope,
    SourceExcerpt,
    Status,
    Summary,
    TaskReport,
    VerificationResult,
    uid,
)
from .decision import Decisions
from .human import Humans
from .integrations.drawing import register_drawing_tools
from .integrations.freecad import register_freecad_tools
from .integrations.mbd import register_mbd_tools
from .integrations.sysml.registry import SysMLRegistry
from .integrations.sysml.runtime import standard_library
from .library import Library, register_library_tools
from .reviews import Reviews
from .standards import parse, squash
from .storage import Store
from .tools.execution import Executor, Job
from .tools.registry import Tool, ToolRegistry, encode

if TYPE_CHECKING:
    from .agents.runtime import Runtime
    from .agents.watchdog import Watchdog
    from .middleware import ContextMiddleware

# Measured by examples/qualification/qualify.py; they route worker tasks to tiers.
QUALIFICATIONS_FILE = Path(__file__).with_name("qualifications.json")
QUALIFICATIONS = TypeAdapter(tuple[Qualification, ...]).validate_json(
    QUALIFICATIONS_FILE.read_bytes()
)


def worker_tiers(provider: ReasoningProvider | None) -> dict[str, ReasoningProvider]:
    """Copies of the provider at each of its tier_profiles' model and effort."""
    tiers, profiles = {}, getattr(provider, "tier_profiles", {})
    for key, (model, effort, capacity) in profiles.items():
        tier = copy.copy(provider)
        vars(tier).update(model=model, effort=effort, context_capacity_tokens=capacity)
        tiers[key] = tier
    return tiers


class Project:
    def __init__(
        self,
        workspace: Path,
        *,
        sandbox: Path | None = None,
        tools: ToolRegistry | None = None,
        reasoning: ReasoningProvider | None = None,
        watchdog: "Watchdog | None" = None,
        systems_engineer: SystemsEngineer | None = None,
        middleware: "Sequence[ContextMiddleware]" = (),
        max_concurrent_calls: int = 4,
        read_only: bool = False,
        library: Library | None = None,
    ) -> None:
        if max_concurrent_calls < 1:
            raise ValueError("max_concurrent_calls must be at least 1")
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
            for name, annotation in (
                ("TaskReport@1", TaskReport),
                ("Note@1", Note),
                ("AskHuman@1", AskHuman),
            ):
                if name not in self.tools.schemas:
                    self.tools.schema(name, annotation)
            # Every project's agents get the CAD integrations: FreeCAD, drawings, MBD.
            if not any(d.grant.name == "draw_part" for d in self.tools.definitions()):
                register_freecad_tools(self)
                register_drawing_tools(self)
                register_mbd_tools(self)
            # The shared reference library, owned by the caller; the project's own
            # scope lives in its workspace. Agents get readers once either is in use.
            self.library = library
            self._project_library: Library | None = None
            if library is not None or (workspace / "library").exists():
                self._library_readers()
            self.reasoning = reasoning
            # Cheaper copies of the provider that workers may run on, and the measured
            # records that route a task family to one; see TaskAuthorization.tier.
            self.tiers = worker_tiers(reasoning)
            self.qualifications = QUALIFICATIONS
            self.watchdog = watchdog
            # Every project runs a Systems Engineer; None uses the defaults.
            self.systems_engineer = systems_engineer or SystemsEngineer()
            self.middleware = tuple(middleware)
            # Agents' model calls in flight at once; the rest queue (provider rate limits).
            self.max_concurrent_calls = max_concurrent_calls
            self.activity = Activity(self.store, self.tools)
            self.human = Humans(self)
            self.contexts = ContextBuilder(
                self.store, self.activity, self.tools, self.verify_file
            )
            self.decisions = Decisions(self)
            self.reviews = Reviews(self)
            self.executor = Executor(self)
            self.sysml = SysMLRegistry(self)
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
        if self._project_library is not None:
            self._project_library.close()
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
            or path.suffix
            in {
                ".json",
                ".toml",
                ".py",
                ".md",
                ".yaml",
                ".yml",
                ".csv",
                ".sysml",
                ".kerml",
            }
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

    @property
    def project_library(self) -> Library:
        """The project's own library scope, kept in its workspace: client specs, site data."""
        if self._project_library is None:
            self._project_library = Library(
                self.store.directory / "library", scope="project"
            )
        return self._project_library

    @property
    def libraries(self) -> dict[Scope, Library]:
        """Attached libraries by scope, the shared one first."""
        scopes: dict[Scope, Library] = {}
        if self.library is not None:
            scopes["shared"] = self.library
        scopes["project"] = self.project_library
        return scopes

    def _library_readers(self) -> None:
        if not any(d.grant.name == "get_element" for d in self.tools.definitions()):
            register_library_tools(self)

    def pin(
        self, snapshot: str, *, source_id: str | None = None, actor: str = "script"
    ) -> Ref:
        """Record the project's binding to a library snapshot as a source.

        A standard's text points at the returned ref. One pin per designation:
        pinning another snapshot of it revises the pin, so everything quoting the
        old one goes stale for reassessment. Pinning the current one again is a no-op.
        """
        for scope, library in self.libraries.items():
            try:
                found = library.snapshot(snapshot)
            except KeyError:
                continue
            break
        else:
            raise KeyError(f"No library attached to this project holds {snapshot}")
        pin = LibraryPin(
            snapshot=found.id,
            scope=scope,
            designation=found.designation,
            edition=found.edition,
            name=found.file_name,
            sha256=found.file_sha256,
            label=found.label,
        )
        id = source_id or f"library:{_squash(found.designation)}"
        current = self.store.maybe("source", id)
        if (
            current is not None
            and not current.stale
            and current.data == pin.model_dump(mode="json")
        ):
            return current.ref
        self._library_readers()
        return self.store.put("source", id, pin, actor=actor)

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
            or not _quoted(requirement.source_quote, text)
        ):
            raise ValueError(
                f"{requirement.id}: quotation must be present in its cited source"
            )
        dependencies = [requirement.source]
        if (withdrawal := requirement.withdrawn) is not None:
            # Only a human retires a requirement, in words its source holds.
            said = self.store.resolve(withdrawal.source, current=True)
            if (
                withdrawal.source.kind != "source"
                or self.store.maybe("requirement", requirement.id) is None
                or not _quoted(withdrawal.quote, str(said.data.get("text") or ""))
            ):
                raise ValueError(
                    f"Withdrawing {requirement.id} needs it recorded first and a human "
                    "statement quoted from a source that says it no longer applies"
                )
            dependencies.append(withdrawal.source)
        if (fact := requirement.fact) is not None:
            stated = squash(requirement.source_quote)
            value = fact.value
            numbers = {float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", stated)}
            if (
                isinstance(value, str)
                and squash(value) not in stated
                or isinstance(value, float | int)
                and float(value) not in numbers
                or squash(fact.unit) not in stated
            ):
                raise ValueError(
                    f"{requirement.id} states fact {fact.name} = {value!r} "
                    f"{fact.unit}, which its quote does not say"
                )
        if (pin := requirement.standard) is not None:
            stated = _squash(
                f"{requirement.source_quote} {source.data.get('question') or ''}"
            )
            if _squash(pin.id) not in stated or _squash(pin.edition) not in stated:
                raise ValueError(
                    f"{requirement.id} selects {pin.id}:{pin.edition}, which its quote "
                    "does not state; ask the human to confirm the standard and edition"
                )
            for other in self.store.list("requirement"):
                record = Requirement.model_validate_json(encode(other.data))
                selected = record.standard
                if (
                    selected
                    and not other.stale
                    and not record.withdrawn
                    and other.ref.id != requirement.id
                    and _squash(selected.id) == _squash(pin.id)
                ):
                    raise ValueError(
                        f"{other.ref.id} already selects {pin.id}; revise it instead"
                    )
            if (pin.text and pin.text.kind != "source") or any(
                r.kind not in {"requirement", "source"} for r in pin.basis
            ):
                raise ValueError(
                    "A standard's text is a source; its basis cites requirements and sources"
                )
            dependencies += [*([pin.text] if pin.text else []), *pin.basis]
        if (clause := requirement.clause) is not None:
            selection = self.store.resolve(clause.standard, current=True)
            selecting = (
                Requirement.model_validate_json(encode(selection.data))
                if clause.standard.kind == "requirement"
                else None
            )
            selected = selecting.standard if selecting else None
            if selecting and selecting.withdrawn and not requirement.withdrawn:
                raise ValueError(
                    f"{clause.standard.id} withdrew {selected.id if selected else 'it'}: "
                    f"withdraw {requirement.id} too"
                )
            if selected is None or selected.text is None:
                raise ValueError(
                    "A clause cites the current requirement selecting its standard, "
                    "recorded with the standard's licensed text"
                )
            licensed = selected.text
            quoted = {
                (r.kind, r.id, r.revision)
                for r in (requirement.source, *source.dependencies)
            }
            if (licensed.kind, licensed.id, licensed.revision) not in quoted:
                raise ValueError(
                    f"Quote clause {clause.reference} from the licensed text of "
                    f"{selected.id} or an excerpt of it"
                )
            dependencies.append(clause.standard)
        return self.store.put(
            "requirement",
            requirement.id,
            requirement,
            actor=actor,
            dependencies=tuple(dict.fromkeys(dependencies)),
        )

    def record_catalogue(self, source: Ref, *, actor: str = "script") -> Ref:
        """Record the project's standards catalogue from a source holding it as JSON.

        A reviewed source, not agent output: its rules decide which standards a
        review requires (Reviews.checks). Every rule must parse.
        """
        text = self.store.resolve(source, current=True).data.get("text")
        if source.kind != "source" or not isinstance(text, str):
            raise ValueError("A catalogue is recorded from a source holding its text")
        catalogue = Catalogue.model_validate_json(text)
        for entry in catalogue.entries:
            if entry.applies_when:
                parse(entry.applies_when)
        return self.store.put(
            "catalogue", "standards", catalogue, actor=actor, dependencies=(source,)
        )

    def record_open_item(self, item: OpenItem, *, actor: str = "script") -> Ref:
        tracked = []
        for id in item.requirements:
            requirement = self.store.maybe("requirement", id)
            if requirement is None or requirement.stale:
                raise ValueError(f"{item.id}: {id} is not a current requirement")
            tracked.append(requirement.ref)
        # A revised requirement stales the item, so its new unknowns block again.
        return self.store.put(
            "open_item",
            item.id,
            item,
            actor=actor,
            dependencies=(*item.resolved_by, *tracked),
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

    def compact(self, agent_id: str, summary: Summary, *, actor: str) -> Ref:
        """Replace an agent's optional sources and summaries with one citing them."""
        ref = self.summarize(summary, actor=actor)
        agent = self.store.model("agent", agent_id, AgentSpec)
        context = agent.context.model_copy(
            update={
                "summaries": (
                    *(r for r in agent.context.summaries if r not in summary.sources),
                    ref,
                ),
                "selected": tuple(
                    r for r in agent.context.selected if r not in summary.sources
                ),
            }
        )
        self.store.put(
            "agent",
            agent_id,
            agent.model_copy(update={"context": context}),
            actor="runtime",
        )
        return ref

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
        if extra := [ref for ref in evidence.artifacts if ref not in inputs]:
            # Name them: a worker re-sent the same claim, its plan said "cite all".
            raise ValueError(
                "Verification must actually depend on every claimed artifact "
                f"revision; request {request.id} did not take "
                + ", ".join(f"{ref.id} rev {ref.revision}" for ref in extra)
            )
        if any(ref.kind != "artifact" for ref in evidence.artifacts) or any(
            ref.kind != "requirement" for ref in evidence.requirements
        ):
            raise ValueError("Evidence references have incorrect record types")
        if (
            evidence.outcome != verification.outcome
            or evidence.explanation != verification.explanation
        ):
            raise ValueError(
                "Evidence must preserve the actual verification result: copy its "
                "outcome and explanation exactly; add commentary in the rationale"
            )
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
        plan_ref = self.store.get("decision", decision_id).ref
        current = self.store.maybe("deliverable", deliverable.spec_id)
        if (
            current is not None
            and not current.stale
            and plan_ref in current.dependencies
            and (stored := Deliverable.model_validate_json(encode(current.data)))
            and (stored.artifacts, stored.evidence)
            == (deliverable.artifacts, deliverable.evidence)
        ):
            # A Chief re-delivered an unchanged package, paying a turn for nothing.
            raise ValueError(
                f"{deliverable.spec_id} is already delivered with these artifacts and "
                f"evidence (revision {current.ref.revision}); deliver again only when "
                "they change"
            )
        return self.store.put(
            "deliverable",
            deliverable.spec_id,
            deliverable,
            actor=actor,
            dependencies=(
                *deliverable.artifacts,
                *deliverable.evidence,
                plan_ref,
            ),
        )

    async def run(
        self, request: ProjectRequest | None = None, *, resume: str | None = None
    ) -> ProjectResult:
        from .agents.runtime import Runtime

        if self.reasoning is None:
            self.store.event(
                "runtime",
                "run.blocked",
                resume or "intake",
                {"reason": "Missing reasoning provider"},
            )
            raise RuntimeError("Configure a reasoning provider before autonomous work")
        if self.runtime is not None:
            raise RuntimeError("A project run is already active")
        # Without the SysML Toolkit the Systems Engineer can never commit a model, so
        # every decision blocks while it spends its budget retrying.
        import sysml
        from sysml.toolkit import Library

        try:
            standard_library()
            Library()
        except (sysml.SdkError, OSError) as exc:
            raise RuntimeError(f"The Systems Engineer needs the SysML Toolkit: {exc}")
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


_squash = squash  # Case- and space-insensitive, so "AS1210" states "AS 1210"


def _quoted(quote: str, text: str) -> bool:
    """Verbatim up to whitespace: briefs hard-wrap, so quotes span line breaks."""
    quote = " ".join(quote.split())
    return bool(quote) and quote in " ".join(text.split())
