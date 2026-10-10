from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .services import rules

CategoryId = Literal[
    "services_australia", "immigration", "ndis", "aged_care", "ato_nbn_dva", "flags_messages",
    "general",
]


class TriageIn(BaseModel):
    notes: str = Field("", max_length=20000)
    category: CategoryId | None = None
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("data")
    @classmethod
    def known_fields_only(cls, v: dict[str, Any]) -> dict[str, Any]:
        return {k: val for k, val in v.items() if k in rules.FIELD_BY_ID}


class SearchIn(BaseModel):
    q: str = Field(..., min_length=1, max_length=200)
    category: CategoryId | None = None
    domains: list[str] | None = None


class TemplateIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    category: CategoryId
    tags: list[str] = Field(default_factory=list)
    summary: str = Field("", max_length=1000)
    sms: str = Field("", max_length=1000)
    body: str = Field("", max_length=20000)
    source_urls: list[str] = Field(default_factory=list)


class TemplatePatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    category: CategoryId | None = None
    tags: list[str] | None = None
    summary: str | None = Field(None, max_length=1000)
    sms: str | None = Field(None, max_length=1000)
    body: str | None = Field(None, max_length=20000)
    source_urls: list[str] | None = None


class GenerateIn(BaseModel):
    kind: Literal["acknowledgement", "resolution"] = "acknowledgement"
    category: CategoryId = "general"
    data: dict[str, Any] = Field(default_factory=dict)
    notes: str = Field("", max_length=20000)
    template_ids: list[int] = Field(default_factory=list)
    polish: bool = True


class JotformIn(BaseModel):
    category: CategoryId = "general"
    data: dict[str, Any] = Field(default_factory=dict)
    notes: str = Field("", max_length=20000)
    urgency: str = ""


class CaseIn(BaseModel):
    client_id: str = Field(..., min_length=4, max_length=64)
    category: CategoryId = "general"
    mode: Literal["resolve", "escalate"] = "resolve"
    data: dict[str, Any] = Field(default_factory=dict)
    notes: str = Field("", max_length=20000)
    draft: str = Field("", max_length=20000)
    status: Literal["open", "resolved", "lodged"] = "open"
