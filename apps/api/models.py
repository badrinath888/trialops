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


class Assignment(Model):
    owner_id: UUID | None = None
    due_at: datetime | None = None

    @field_validator("due_at")
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
