from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, StringConstraints, Field, field_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Category = Literal[
    "synchronization", "document_workflow", "access", "signature", "training", "unknown"
]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credentials(Model):
    email: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=5, max_length=254)
    ]
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def email_check(cls, v):
        import re

        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", v):
            raise ValueError("Enter a valid email address")
        return v.lower()


class Register(Credentials):
    name: Text = Field(max_length=100)


class NewCase(Model):
    title: Text = Field(min_length=5, max_length=200)
    description: Text = Field(min_length=10, max_length=4000)
    study_id: Text = Field(max_length=50)
    site_id: Text = Field(max_length=50)
    category: Category
    priority: Literal["low", "medium", "high"]
    due_at: datetime | None = None
    submission_id: UUID | None = None

    @field_validator("due_at")
    @classmethod
    def aware(cls, v):
        if v and v.tzinfo is None:
            raise ValueError("Timezone required")
        return v


class Classification(Model):
    title: Text = Field(min_length=5, max_length=200)
    description: Text = Field(min_length=10, max_length=4000)


class Knowledge(Model):
    title: Text = Field(min_length=5, max_length=200)
    content: Text = Field(min_length=30, max_length=50000)
    category: Category
    expected_version: int | None = Field(default=None, ge=1)


class Decision(Model):
    decision: Literal["approved", "rejected"]
    notes: Text = Field(min_length=5, max_length=2000)


class Note(Model):
    notes: Text = Field(min_length=10, max_length=2000)


class Resolve(Note):
    run_id: UUID
    confirmed: Literal[True]
    verified_at: datetime
    evidence_refs: list[UUID] = Field(min_length=1, max_length=50)
    exceptions: str = Field(default="", max_length=4000)
    expected_updated_at: datetime

    @field_validator("verified_at", "expected_updated_at")
    @classmethod
    def aware(cls, v):
        if v.tzinfo is None:
            raise ValueError("Timezone required")
        return v


class Assignment(Model):
    expected_updated_at: datetime | None = None
    owner_id: UUID | None = None
    due_at: datetime | None = None

    @field_validator("due_at", "expected_updated_at")
    @classmethod
    def aware(cls, v):
        if v and v.tzinfo is None:
            raise ValueError("Timezone required")
        return v


class Scenario(Model):
    baseline: float = Field(ge=0, le=1440)
    assisted: float = Field(ge=0, le=1440)
    hourly_cost: float = Field(ge=0, le=10000)
    ai_cost: float = Field(ge=0, le=10000)
    confirmed: Literal[True]


class Feedback(Model):
    rating: int = Field(ge=1, le=5)
    message: Text = Field(min_length=10, max_length=2000)


class Invite(Model):
    role: Literal["reviewer", "analyst"]


class InviteAccept(Model):
    code: Text = Field(max_length=128)


class Switch(Model):
    workspace_id: UUID


class Operations(Model):
    study_id: Text = Field(max_length=50)
    site_id: Text = Field(max_length=50)
    evidence: dict


class Archive(Model):
    archived: bool
    expected_version: int = Field(ge=1)


Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{1,49}$"
    ),
]


class Study(Model):
    id: Identifier
    name: Text = Field(min_length=3, max_length=200)


class Site(Study):
    study_id: Identifier


# Integrated workflows use explicit versions to reject stale edits.
class Versioned(Model):
    expected_version: int = Field(ge=1)


class CheckItem(Model):
    id: UUID
    text: Text = Field(max_length=50000)
    source_id: Text = Field(max_length=200)
    suggestion: bool = True
    state: Literal["not_checked", "verified", "needs_follow_up", "not_applicable"] = (
        "not_checked"
    )
    notes: str = Field(default="", max_length=4000)
    evidence_refs: list[UUID] = Field(default_factory=list, max_length=30)
    actor_id: str | None = None
    actor_name: str | None = None
    recorded_at: str | None = None


class CheckEdit(Versioned):
    items: list[CheckItem] = Field(min_length=1, max_length=50)
    due_at: datetime | None = None
    _aware = field_validator("due_at")(Assignment.aware.__func__)


class RequestCreate(Model):
    id: UUID
    contact_id: UUID | None = None
    duplicate_reason: str = Field(default="", max_length=2000)
    run_id: UUID
    title: Text = Field(min_length=5, max_length=200)
    items: list[
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=3, max_length=2000)
        ]
    ] = Field(min_length=1, max_length=30)
    owner_id: UUID | None = None
    due_at: datetime | None = None
    _aware = field_validator("due_at")(Assignment.aware.__func__)


class RequestEdit(Versioned):
    contact_id: UUID | None = None
    duplicate_reason: str = Field(default="", max_length=2000)
    title: Text = Field(min_length=5, max_length=200)
    items: list[
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=3, max_length=2000)
        ]
    ] = Field(min_length=1, max_length=30)
    owner_id: UUID | None = None
    due_at: datetime | None = None
    status: Literal["draft", "requested", "received", "cancelled"]
    response: str = Field(default="", max_length=4000)
    evidence_refs: list[UUID] = Field(default_factory=list, max_length=30)
    _aware = field_validator("due_at")(Assignment.aware.__func__)


class EvidenceCreate(Model):
    id: UUID
    kind: Literal["human_observation", "snapshot", "request_response"]
    reference_id: str | None = Field(default=None, max_length=200)
    summary: Text = Field(min_length=10, max_length=4000)
    observed_at: datetime
    _aware = field_validator("observed_at")(Assignment.aware.__func__)


class ComparisonCreate(Model):
    before_id: UUID
    after_id: UUID


class RelatedLink(Model):
    related_id: Text = Field(max_length=100)
    rationale: Text = Field(min_length=10, max_length=2000)
    confirmed: Literal[True]


class EffortCreate(Model):
    id: UUID
    run_id: UUID | None = None
    minutes: float = Field(gt=0, le=1440)
    activity: Literal["investigation", "review", "follow_up", "resolution"]
    notes: Text = Field(min_length=5, max_length=2000)


class PolicyEdit(Versioned):
    freshness_hours: float | None = Field(default=None, gt=0, le=87600)
    reminder_lead_hours: int = Field(default=24, ge=0, le=168)
    reminder_frequency_minutes: int = Field(default=60, ge=15, le=10080)
    visit_checklist: list[
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)
        ]
    ] = Field(default_factory=list, max_length=50)


class ReassessmentEdit(Versioned):
    status: Literal["needed", "not_needed"]
    rationale: Text = Field(min_length=10, max_length=2000)


class VisitItem(Model):
    id: UUID
    text: Text = Field(max_length=2000)
    state: Literal["not_checked", "verified", "needs_follow_up", "not_applicable"] = (
        "not_checked"
    )
    notes: str = Field(default="", max_length=2000)
    actor_id: str | None = None
    actor_name: str | None = None
    recorded_at: str | None = None


class VisitCreate(Model):
    id: UUID
    study_id: Identifier
    site_id: Identifier
    visit_at: datetime
    title: Text = Field(min_length=5, max_length=200)
    _aware = field_validator("visit_at")(Assignment.aware.__func__)


class VisitEdit(Versioned):
    checklist: list[VisitItem] = Field(max_length=50)
    visit_at: datetime
    _aware = field_validator("visit_at")(Assignment.aware.__func__)


class ImportPreview(Model):
    format: Literal["csv", "json"]
    content: Text = Field(max_length=100000)
    mapping: dict[str, str] = Field(default_factory=dict, max_length=50)


class ImportCommit(Model):
    confirmed: Literal[True]


class NotificationPrefs(Model):
    enabled: bool
    kinds: list[Literal["request", "check", "reassessment", "deadline"]] = Field(
        max_length=4
    )


class EvaluationCreate(Model):
    id: UUID
    mode: Literal["procedure", "ollama"]
    suite: Literal["investigation", "assessments"] = "investigation"


class WalkthroughUpdate(Model):
    step: int = Field(ge=0, le=6)
    skipped: bool = False
