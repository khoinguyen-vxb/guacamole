"""Validated, domain-independent wire contracts. Domain types belong to tools."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

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


class VerificationResult(Model):
    """An explicit physical/test acceptance result, distinct from tool completion."""

    outcome: Literal["passed", "failed", "unperformed", "inconclusive"]
    explanation: str
    checks: dict[str, bool | None]

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


class ContextPacket(Model):
    id: str = Field(default_factory=uid)
    agent_id: str
    invocation_id: str
    request_id: str
    provider: str
    model: str
    prompt: str
    input_tokens: int = Field(ge=0)
    reserved_output_tokens: int = Field(gt=0)
    sources: tuple[Ref, ...] = ()
    message_ids: tuple[str, ...] = ()
    deferred: tuple[Omission, ...] = ()
    created_at: str = Field(default_factory=now)


class Budget(Model):
    max_steps: int = Field(default=40, gt=0)
    max_tool_calls: int = Field(default=30, ge=0)
    max_seconds: float = Field(default=600.0, gt=0)
    max_agents: int = Field(default=12, ge=0)


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


class Quantity(Model):
    value: float
    unit: str
    frame: str | None = None


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


class ReferencedData(Model):
    ref: Ref
    content: JSON


class DecisionRequest(Model):
    question: str
    kind: Literal["work_plan", "engineering", "review"]
    candidates: tuple[Candidate, ...] = Field(min_length=1)
    constraints: tuple[Constraint, ...] = ()
    criteria: tuple[str, ...] = Field(min_length=1)
    assumptions: tuple[str, ...] = ()
    evidence: tuple[Ref, ...] = ()
    context: tuple[ReferencedData, ...] = ()


class DecisionResult(Model):
    request_id: str
    selected: str | None
    explanation: str = Field(min_length=1)
    evidence: tuple[Ref, ...] = ()
    provider_request_id: str | None = None


class DecisionRecord(Model):
    request: DecisionRequest
    result: DecisionResult
    provider: str
    version: str
    is_test_double: bool
    accepted: bool


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
    kind: Literal["tool", "agent", "peer", "decision", "review"]
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


class TaskReport(Model):
    summary: str
    evidence: tuple[Ref, ...] = ()
    unresolved: tuple[str, ...] = ()


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
    readiness_decision: str | None = None
    human: str | None = None
    disposition: str | None = None
    test_only: bool = False


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
    status: Literal["incomplete", "awaiting_review", "complete"]
    reviews: tuple[Ref, ...] = ()
    open_items: tuple[str, ...] = ()
    test_only: bool = False


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


class Acknowledge(Model):
    kind: Literal["acknowledge"] = "acknowledge"
    message_id: str


class Decide(Model):
    kind: Literal["decide"] = "decide"
    request: DecisionRequest


class Spawn(Model):
    kind: Literal["spawn"] = "spawn"
    decision_id: str
    task_id: str
    context: ContextSpec | None = None


class Record(Model):
    kind: Literal["record"] = "record"
    record: Requirement | OpenItem


class Publish(Model):
    kind: Literal["publish"] = "publish"
    path: str
    artifact_id: str
    artifact_kind: str
    tool_request: str
    inputs: tuple[Ref, ...]
    requirements: tuple[Ref, ...]


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


type Action = Annotated[
    ToolCall
    | Send
    | Acknowledge
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
    | Retry,
    Field(discriminator="kind"),
]


class AgentTurn(Model):
    rationale: Rationale
    action: Action
    provider_request_id: str | None = None
    provider_summary: str | None = None
