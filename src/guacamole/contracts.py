"""Validated, domain-independent wire contracts. Domain types belong to tools."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    JsonValue,
    model_validator,
)
from pydantic.json_schema import SkipJsonSchema

type JSON = dict[str, JsonValue]
type ReviewStage = Literal["PDR", "CDR"]
type Status = Literal[
    "queued",
    "dispatched",
    "running",
    "completed",
    "failed",
    "blocked",
    "expired",
    "interrupted",
    "uncertain",
    "cancel_requested",
    "cancelled",
]
TERMINAL = {"completed", "failed", "expired", "interrupted", "uncertain", "cancelled"}


def uid() -> str:
    return uuid4().hex


def now() -> str:
    return datetime.now(UTC).isoformat()


class Model(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
        revalidate_instances="always",
        validate_default=True,
    )


class Ref(Model):
    kind: str
    id: str
    revision: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    locator: str = ""


class FileRecord(Model):
    name: str
    path: str
    sha256: str
    media_type: str
    origin: str
    text: str | None = None
    metadata: JSON = Field(default_factory=dict)
    missing_metadata: tuple[str, ...] = ()
    producer_request: str | None = None


class ProducedFile(Model):
    """A file returned by a tool; the executor snapshots it before job success."""

    kind: Literal["produced_file"] = "produced_file"
    path: str
    sha256: str

    @classmethod
    def from_path(cls, path: Path) -> "ProducedFile":
        import hashlib

        return cls(
            path=str(path.resolve()),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )


class Quantity(Model):
    value: float
    unit: str
    frame: str | None = None


class VerificationResult(Model):
    """An explicit physical/test acceptance result, distinct from tool completion.

    A check or measurement keyed by a requirement id ("R1: mass <= 0.5 kg",
    measurements["R1"]) traces to that requirement in the review report.
    """

    outcome: Literal["passed", "failed", "unperformed", "inconclusive"]
    explanation: str
    checks: dict[str, bool | None]
    measurements: dict[str, Quantity] = Field(default_factory=dict)

    @model_validator(mode="after")
    def consistent(self) -> "VerificationResult":
        if self.outcome == "passed" and (
            not self.checks or not all(v is True for v in self.checks.values())
        ):
            raise ValueError("Passed verification requires observed passing checks")
        return self


class SourceExcerpt(Model):
    source: Ref
    locator: str = Field(min_length=1)
    text: str
    metadata: JSON = Field(default_factory=dict)
    missing_metadata: tuple[str, ...] = ()


class Summary(Model):
    text: str
    sources: tuple[Ref, ...] = Field(min_length=1)


class ContextSpec(Model):
    instructions: str = ""
    selected: tuple[Ref, ...] = ()
    pinned: tuple[Ref, ...] = ()
    max_input_tokens: int = Field(default=32_000, gt=0)
    reserved_output_tokens: int = Field(default=4_000, gt=0)
    search: str = ""
    max_search_results: int = Field(default=8, ge=0, le=100)
    summaries: tuple[Ref, ...] = ()


class Omission(Model):
    item: str
    reason: str


class ImageAttachment(Model):
    """A file's pixels sent with one invocation; the provider re-checks its hash."""

    source: Ref  # The source, job_file or artifact record holding the file
    path: str  # Absolute; verified inside project storage when assembled
    sha256: str
    media_type: str  # image/png, image/jpeg or image/webp


class ContextPacket(Model):
    id: str = Field(default_factory=uid)
    agent_id: str
    invocation_id: str
    request_id: str
    provider: str
    model: str
    prompt: str
    input_tokens: int = Field(ge=0)
    token_count_method: Literal[
        "exact",
        "utf8_upper_bound",
        "tiktoken_o200k_base_estimate_10pct_plus_1024",
        "litellm_estimate_10pct_plus_1024",
    ] = "exact"
    reserved_output_tokens: int = Field(gt=0)
    sources: tuple[Ref, ...] = ()
    # Sent in this order; the prompt marks their sources "image": "attached".
    images: tuple[ImageAttachment, ...] = ()
    message_ids: tuple[str, ...] = ()
    deferred: tuple[Omission, ...] = ()
    # Prompt prefix lengths, in characters, that stay identical across turns;
    # providers may cache them. Later prefixes change more often.
    cache_breakpoints: tuple[int, ...] = ()
    # Characters each prompt component takes, to find what dominates input.
    components: dict[str, int] = Field(default_factory=dict)
    created_at: str = Field(default_factory=now)


class Usage(Model):
    """Provider-reported tokens for invocations; None where a provider reports none."""

    input_tokens: int | None = None  # Neither read from nor written to a cache
    cache_read_input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    output_tokens: int | None = None  # Includes reasoning
    cost_usd: float | None = None

    def __add__(self, other: "Usage") -> "Usage":
        totals: JSON = {}
        for name in Usage.model_fields:
            values = [
                v for v in (getattr(self, name), getattr(other, name)) if v is not None
            ]
            totals[name] = sum(values) if values else None
        return Usage.model_validate(totals)


class Budget(Model):
    max_steps: int = Field(default=40, gt=0)
    max_tool_calls: int = Field(default=30, ge=0)
    max_seconds: float = Field(default=600.0, gt=0)
    # Workers running at once; completed and superseded ones free their slot.
    max_agents: int = Field(default=12, ge=0)
    # Run-wide cap on estimated agent prompt tokens, failed calls included (the
    # watchdog's own calls are not counted); None is unlimited.
    max_run_input_tokens: int | None = Field(default=None, gt=0)


class ToolGrant(Model):
    name: str
    version: str = "1"

    @property
    def key(self) -> str:
        return f"{self.name}@{self.version}"


class TaskAuthorization(Model):
    id: str
    objective: str = Field(min_length=1)
    tools: tuple[ToolGrant, ...] = ()
    result_schema: str = "TaskReport@1"
    completion_criteria: tuple[str, ...] = ()
    peers: tuple[str, ...] = ()
    budget: Budget = Field(default_factory=Budget)
    depends_on: tuple[str, ...] = ()
    # Kind of work, e.g. extraction or diagnosis; the runtime gives it the cheapest
    # tier qualified for that family. tier overrides that choice: a Project.tiers
    # key, where None leaves the choice to the family (the Chief's model if unqualified).
    family: str | None = None
    tier: str | None = None


class Qualification(Model):
    """Measured outcome of one reasoning profile on one task family."""

    family: str
    provider: str
    model: str
    effort: str | None = None
    trials: int = Field(ge=1)
    passed: int = Field(ge=0)  # Completed and independently verified
    cost_usd: float | None = None  # Totals over all trials
    seconds: float = 0.0
    turns: int = 0
    rejected_actions: int = 0
    measured_at: str = Field(default_factory=now)

    @model_validator(mode="after")
    def bounded(self) -> "Qualification":
        if self.passed > self.trials:
            raise ValueError("More passes than trials")
        return self


class DeliverableSpec(Model):
    id: str
    title: str
    stage: ReviewStage
    requirements: tuple[Ref, ...]
    artifact_kinds: tuple[str, ...] = Field(min_length=1)
    evidence_kinds: tuple[str, ...] = ()
    required_tools: tuple[ToolGrant, ...] = ()
    acceptance_criteria: tuple[str, ...] = Field(min_length=1)


class WorkPlan(Model):
    stage: ReviewStage
    tasks: tuple[TaskAuthorization, ...] = ()
    chief_tools: tuple[ToolGrant, ...] = ()
    deliverables: tuple[DeliverableSpec, ...] = Field(min_length=1)
    inputs: tuple[Ref, ...] = ()


class Constraint(Model):
    metric: str
    unit: str
    minimum: float | None = None
    maximum: float | None = None

    @model_validator(mode="after")
    def ordered(self) -> "Constraint":
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError("Constraint minimum exceeds maximum")
        return self


class Requirement(Model):
    id: str
    wording: str
    source: Ref
    source_quote: str
    constraint: Constraint | None = None
    target: Quantity | None = None
    unknowns: tuple[str, ...] = ()


class OpenItem(Model):
    id: str
    description: str
    kind: Literal["missing_input", "missing_tool", "assumption", "risk", "test_due"]
    blocking_stages: tuple[ReviewStage, ...] = ("PDR", "CDR")
    resolved_by: tuple[Ref, ...] = ()


class Candidate(Model):
    id: str
    description: str
    metrics: dict[str, Quantity] = Field(default_factory=dict)
    evidence: tuple[Ref, ...] = ()
    consequences: tuple[str, ...] = ()
    plan: WorkPlan | None = None


def _context_ref(entry: object) -> object:
    """Older decisions stored {ref, content} context entries; read them as their refs."""
    return entry["ref"] if isinstance(entry, dict) and "ref" in entry else entry


class DecisionRequest(Model):
    question: str
    kind: Literal["work_plan", "engineering"]
    candidates: tuple[Candidate, ...] = Field(min_length=1)
    constraints: tuple[Constraint, ...] = ()
    criteria: tuple[str, ...] = Field(min_length=1)
    assumptions: tuple[str, ...] = ()
    evidence: tuple[Ref, ...] = ()
    # Every record the choice transitively rests on. Refs, not copies: a copy nested
    # earlier decisions' copies, so each decision outgrew the last (1.5 MB, 3.5 MB).
    context: tuple[Annotated[Ref, BeforeValidator(_context_ref)], ...] = ()


class DecisionResult(Model):
    request_id: str
    selected: str
    explanation: str = Field(min_length=1)
    evidence: tuple[Ref, ...] = ()


class DecisionRecord(Model):
    request: DecisionRequest
    result: DecisionResult
    author: str
    model: Ref | None = None  # SysML model revision the choice was validated against


class Rationale(Model):
    objective: str
    explanation: str = Field(min_length=1)
    assumptions: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()
    evidence: tuple[Ref, ...] = ()
    uncertainty: tuple[str, ...] = ()
    supersedes: str | None = None


class RationaleRecord(Model):
    id: str = Field(default_factory=uid)
    author: str
    invocation_id: str
    packet_id: str
    request_id: str
    content: Rationale
    origin: Literal["agent_summary", "provider_summary"] = "agent_summary"


class Attempt(Model):
    number: int = Field(ge=1)
    started_at: str = Field(default_factory=now)
    finished_at: str | None = None
    status: Status = "dispatched"
    reason: str | None = None


class RequestRecord(Model):
    id: str = Field(default_factory=uid)
    run_id: str
    requester: str
    target: str
    kind: Literal["tool", "agent", "peer", "decision", "review", "human"]
    arguments: JSON
    purpose: str
    status: Status = "queued"
    parent_id: str | None = None
    decision_id: str | None = None
    rationale_id: str | None = None
    packet_id: str | None = None
    attempts: tuple[Attempt, ...] = ()
    result: JsonValue = None
    reason: str | None = None
    deadline: str | None = None
    required: bool = True
    created_at: str = Field(default_factory=now)

    @model_validator(mode="after")
    def valid_deadline(self) -> "RequestRecord":
        if (
            self.deadline is not None
            and datetime.fromisoformat(self.deadline).tzinfo is None
        ):
            raise ValueError("Request deadlines must include a time zone")
        return self


class MessageEnvelope(Model):
    id: str = Field(default_factory=uid)
    project_id: str
    run_id: str
    sender: str
    recipient: str
    kind: Literal[
        "delegation", "request", "reply", "finding", "question", "cancellation"
    ]
    schema_id: str
    payload: JsonValue
    request_id: str | None = None
    parent_request_id: str | None = None
    reply_to: str | None = None
    context_refs: tuple[Ref, ...] = ()
    created_at: str = Field(default_factory=now)


class InboxEntry(Model):
    message: MessageEnvelope
    delivered_at: str | None = None
    included_packets: tuple[str, ...] = ()
    acknowledged_at: str | None = None
    response_required: bool = False
    response_message_id: str | None = None
    reason: str | None = None


class ActivityEvent(Model):
    sequence: int
    id: str
    timestamp: str
    actor: str
    type: str
    entity_id: str
    request_id: str | None = None
    causal_event: int | None = None
    details: JSON


class AgentSpec(Model):
    id: str = Field(default_factory=uid)
    task_id: str
    parent_id: str | None
    objective: str
    context: ContextSpec
    decision_id: str | None
    tools: tuple[ToolGrant, ...] = ()
    result_schema: str = "TaskReport@1"
    completion_criteria: tuple[str, ...] = ()
    peers: tuple[str, ...] = ()
    budget: Budget = Field(default_factory=Budget)
    tier: str | None = None


class AgentState(Model):
    request_id: str
    status: str = "active"
    steps: int = 0
    tool_calls: int = 0
    elapsed_s: float = 0.0
    observation: JSON = Field(default_factory=dict)


class HumanInput(Model):
    id: str = Field(default_factory=uid)
    run_id: str
    author: str = Field(pattern=r"\S")
    text: str = Field(pattern=r"\S")
    references: tuple[Ref, ...] = ()
    reply_to: str | None = None
    created_at: str = Field(default_factory=now)


class HumanInputs(Model):
    sources: tuple[Ref, ...] = ()


class TaskReport(Model):
    """unresolved: work this task still owes; finishing waits until it is done.
    handoffs: open items owned by the parent or other tasks, returned with the report."""

    summary: str
    evidence: tuple[Ref, ...] = ()
    unresolved: tuple[str, ...] = ()
    handoffs: tuple[str, ...] = ()


class Note(Model):
    text: str
    evidence: tuple[Ref, ...] = ()


class Evidence(Model):
    id: str
    kind: str
    outcome: Literal["passed", "failed", "unperformed", "inconclusive"]
    explanation: str
    artifacts: tuple[Ref, ...]
    requirements: tuple[Ref, ...]
    request_id: str
    decision_id: str


class ArtifactRecord(Model):
    file: FileRecord
    kind: str
    requirements: tuple[Ref, ...]
    inputs: tuple[Ref, ...]
    decision_id: str


class Deliverable(Model):
    spec_id: str
    artifacts: tuple[Ref, ...]
    evidence: tuple[Ref, ...]
    rationale_id: str


class ReviewManifest(Model):
    id: str = Field(default_factory=uid)
    stage: ReviewStage
    plan_decision: str
    baseline: tuple[Ref, ...]
    deliverables: tuple[Deliverable, ...]
    open_items: tuple[str, ...]
    status: Literal["generated", "ready", "accepted", "rejected"] = "generated"
    human: str | None = None
    disposition: str | None = None
    model: Ref | None = None  # SysML model revision under review


class ModelIssue(Model):
    severity: Literal["error", "warning"]
    code: str
    element: str
    detail: str


class ModelBound(Model):
    """A machine-checkable requirement bound read from the SysML model."""

    requirement: str
    metric: str  # Qualified name of the constrained feature
    name: str  # Also a metric key while no other bounded feature shares it
    unit: str  # Unit symbol as written, e.g. "kg" or "m/s^2"; "" is dimensionless
    minimum: float | None = None
    maximum: float | None = None
    exclusive_minimum: bool = False
    exclusive_maximum: bool = False


class ModeledRequirement(Model):
    id: str
    element: str
    text: str
    parent: str | None = None  # Requirement a derived requirement is nested in


class Satisfaction(Model):
    requirement: str
    element: str
    status: Literal["satisfied", "violated", "unverified"]
    detail: str


class ModelReport(Model):
    """Deterministic SysML Toolkit validation of one model revision."""

    valid: bool
    digest: str
    elements: int = 0
    requirements: tuple[ModeledRequirement, ...] = ()
    bounds: tuple[ModelBound, ...] = ()
    satisfactions: tuple[Satisfaction, ...] = ()
    issues: tuple[ModelIssue, ...] = ()


class SystemModel(Model):
    """One committed revision of the authoritative SysML v2 model."""

    files: dict[str, str] = Field(min_length=1)
    summary: str = Field(min_length=1)
    derived_from: tuple[Ref, ...] = ()
    implements: str | None = None
    report: ModelReport
    author: str


class Amendment(Model):
    """A proposed model change that current records do not yet authorize."""

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    files: dict[str, str] = Field(default_factory=dict)
    remove: tuple[str, ...] = ()
    evidence: tuple[Ref, ...] = ()
    supersedes: tuple[str, ...] = ()


class ModelChanges(Model):
    files: tuple[str, ...] = ()
    requirements: tuple[str, ...] = ()
    elements_added: tuple[str, ...] = ()
    elements_removed: tuple[str, ...] = ()
    diff: str = ""


class AmendmentRecord(Model):
    amendment: Amendment
    base: Ref
    report: ModelReport
    changes: ModelChanges
    author: str


class ProjectRequest(Model):
    description: str = Field(min_length=1)
    documents: tuple[Path, ...] = ()
    context: ContextSpec = Field(default_factory=ContextSpec)
    target_reviews: tuple[ReviewStage, ...] = Field(
        default=("PDR", "CDR"), min_length=1
    )
    budget: Budget = Field(default_factory=Budget)


class ProjectResult(Model):
    run_id: str
    status: Literal["incomplete", "awaiting_human", "awaiting_review", "complete"]
    reviews: tuple[Ref, ...] = ()
    human_requests: tuple[str, ...] = ()
    open_items: tuple[str, ...] = ()


class ToolCall(Model):
    kind: Literal["tool"] = "tool"
    tool: ToolGrant
    arguments: JSON
    inputs: tuple[Ref, ...] = ()


class Send(Model):
    kind: Literal["send"] = "send"
    recipient: str
    schema_id: str = "Note@1"
    payload: JsonValue
    request: bool = False
    reply_to: str | None = None

    @model_validator(mode="after")
    def one_obligation(self) -> "Send":
        if self.request and self.reply_to is not None:
            raise ValueError("A reply cannot create a second response obligation")
        return self


def _batched(data: object, into: str, *single: str) -> object:
    """Read a turn recorded before batching: its single item's fields become one entry.

    A before-validator hands strict tuple fields Python lists rather than JSON
    arrays, so lists become tuples here.
    """
    if not isinstance(data, dict):
        return data
    data = {k: tuple(v) if isinstance(v, list) else v for k, v in data.items()}
    if single[0] in data:
        item = {key: data.pop(key) for key in single if key in data}
        data[into] = (item[single[0]] if len(single) == 1 else item,)
    return data


class Acknowledge(Model):
    """Mark messages seen; they leave your context unless a reply is still owed."""

    kind: Literal["acknowledge"] = "acknowledge"
    message_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _single(cls, data: object) -> object:
        return _batched(data, "message_ids", "message_id")


class AskHuman(Model):
    kind: Literal["ask_human"] = "ask_human"
    question: str = Field(pattern=r"\S")
    choices: tuple[str, ...] = ()
    references: tuple[Ref, ...] = ()
    blocking: bool = True


class Decide(Model):
    kind: Literal["decide"] = "decide"
    request: DecisionRequest
    selected: str = Field(min_length=1)


class Spawn(Model):
    kind: Literal["spawn"] = "spawn"
    decision_id: str
    task_id: str
    context: ContextSpec | None = None


class Record(Model):
    kind: Literal["record"] = "record"
    record: Requirement | OpenItem


class PublishedFile(Model):
    path: str
    artifact_id: str
    artifact_kind: str


class Publish(Model):
    """Publish every file one tool run produced, sharing inputs and requirements."""

    kind: Literal["publish"] = "publish"
    files: tuple[PublishedFile, ...] = Field(min_length=1)
    tool_request: str
    inputs: tuple[Ref, ...]
    requirements: tuple[Ref, ...]

    @model_validator(mode="before")
    @classmethod
    def _single(cls, data: object) -> object:
        return _batched(data, "files", "path", "artifact_id", "artifact_kind")


class Verify(Model):
    kind: Literal["verify"] = "verify"
    evidence: Evidence


class Deliver(Model):
    kind: Literal["deliver"] = "deliver"
    spec_id: str
    artifacts: tuple[Ref, ...]
    evidence: tuple[Ref, ...]


class Review(Model):
    kind: Literal["review"] = "review"
    decision_id: str


class Read(Model):
    kind: Literal["read"] = "read"
    refs: tuple[Ref, ...] = ()
    search: str = ""


class Extract(Model):
    kind: Literal["extract"] = "extract"
    tool_request: str


class Compact(Model):
    kind: Literal["compact"] = "compact"
    summary: Summary


class Finish(Model):
    kind: Literal["finish"] = "finish"
    result: JsonValue


class Wait(Model):
    kind: Literal["wait"] = "wait"
    reason: str


class Retry(Model):
    kind: Literal["retry"] = "retry"
    request_id: str
    reason: str = Field(min_length=1)


class Supersede(Model):
    """Settle your failed request with the later completed request that corrected it."""

    kind: Literal["supersede"] = "supersede"
    request_id: str
    by: str
    reason: str = Field(min_length=1)


class UpdateModel(Model):
    kind: Literal["model"] = "model"
    summary: str = Field(min_length=1)
    files: dict[str, str] = Field(default_factory=dict)  # Changed files, full text
    remove: tuple[str, ...] = ()
    derived_from: tuple[Ref, ...] = ()
    implements: str | None = None


class Amend(Model):
    kind: Literal["amend"] = "amend"
    amendment: Amendment


type Action = Annotated[
    ToolCall
    | Send
    | Acknowledge
    | AskHuman
    | Decide
    | Spawn
    | Record
    | Publish
    | Verify
    | Deliver
    | Review
    | Read
    | Extract
    | Compact
    | Finish
    | Wait
    | Retry
    | Supersede
    | UpdateModel
    | Amend,
    Field(discriminator="kind"),
]


class AgentTurn(Model):
    rationale: Rationale
    action: Action
    provider_request_id: str | None = None
    provider_summary: str | None = None
    # Filled by the provider after the call; hidden from the response schema.
    usage: SkipJsonSchema[Usage | None] = None
