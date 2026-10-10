from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .services import taxonomy

MAX_STATE_BYTES = 200_000


def _clean_values(v: dict[str, Any]) -> dict[str, Any]:
    return {k: ("" if val is None else str(val))[:2000] for k, val in v.items()
            if k in taxonomy.FIELD_BY_ID}


class LoginIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=1, max_length=200)


class InteractionState(BaseModel):
    """Staff-controlled record. Everything in here is authoritative over suggestions."""

    model_config = {"extra": "allow"}

    values: dict[str, Any] = Field(default_factory=dict)
    rejected: dict[str, list[str]] = Field(default_factory=dict)
    types: dict[str, list[str]] = Field(default_factory=dict)  # selected / rejected
    team: str | None = None
    summary: dict[str, str] = Field(default_factory=dict)  # issue / outcome
    not_applicable: list[str] = Field(default_factory=list)
    dismissed_questions: list[str] = Field(default_factory=list)
    approved_actions: list[str] = Field(default_factory=list)
    dismissed_actions: list[str] = Field(default_factory=list)
    custom_actions: list[str] = Field(default_factory=list)
    deadlines_accepted: list[dict[str, Any]] = Field(default_factory=list)
    deadlines_dismissed: list[str] = Field(default_factory=list)

    @field_validator("values")
    @classmethod
    def known_values(cls, v: dict[str, Any]) -> dict[str, Any]:
        return _clean_values(v)


class InteractionSave(BaseModel):
    version: int
    notes: str = Field("", max_length=50_000)
    state: InteractionState = Field(default_factory=InteractionState)

    @field_validator("state")
    @classmethod
    def bounded(cls, v: InteractionState) -> InteractionState:
        if len(json.dumps(v.model_dump())) > MAX_STATE_BYTES:
            raise ValueError("record too large")
        return v


class AnalyseIn(BaseModel):
    notes: str = Field("", max_length=50_000)
    state: InteractionState = Field(default_factory=InteractionState)
    model: bool = False
    seq: int = 0


class PrepareIn(BaseModel):
    interaction_id: str = Field(..., max_length=64)
    type_id: str
    form_option: str = Field(..., max_length=120)
    values: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, str] = Field(default_factory=dict)
    approved_actions: list[str] = Field(default_factory=list)
    confirmed_deadlines: list[str] = Field(default_factory=list)
    additional: bool = False

    @field_validator("values")
    @classmethod
    def known_values(cls, v: dict[str, Any]) -> dict[str, Any]:
        return _clean_values(v)


class OpenIn(BaseModel):
    payload_hash: str = Field(..., max_length=64)


class ReportIn(BaseModel):
    submitted: bool
    submission_id: str = Field("", max_length=40)


TypeId = Literal[tuple(t.id for t in taxonomy.ENQUIRY_TYPES)]  # type: ignore[valid-type]


class SearchIn(BaseModel):
    q: str = Field(..., min_length=1, max_length=200)
    type_id: TypeId | None = None
    domains: list[str] | None = None


class TemplateIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    category: TypeId
    tags: list[str] = Field(default_factory=list)
    summary: str = Field("", max_length=1000)
    sms: str = Field("", max_length=1000)
    body: str = Field("", max_length=20000)
    source_urls: list[str] = Field(default_factory=list)


class TemplatePatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    category: TypeId | None = None
    tags: list[str] | None = None
    summary: str | None = Field(None, max_length=1000)
    sms: str | None = Field(None, max_length=1000)
    body: str | None = Field(None, max_length=20000)
    source_urls: list[str] | None = None
    approve: bool = False


class GenerateIn(BaseModel):
    type_id: TypeId = "admin"
    values: dict[str, Any] = Field(default_factory=dict)
    notes: str = Field("", max_length=50_000)
    template_ids: list[int] = Field(default_factory=list)
    polish: bool = True

    @field_validator("values")
    @classmethod
    def known_values(cls, v: dict[str, Any]) -> dict[str, Any]:
        return _clean_values(v)


class GuidanceIn(BaseModel):
    types: list[str] = Field(default_factory=list, max_length=10)
    notes: str = Field("", max_length=50_000)
