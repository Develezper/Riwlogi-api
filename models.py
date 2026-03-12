from pydantic import BaseModel, Field, field_validator
from typing import Literal
from datetime import datetime


class SubmissionEvent(BaseModel):
    type: str
    char_count: int = Field(default=0, ge=0, le=100_000)
    timestamp: str = ""

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, v):
        return str(v or "unknown").strip().lower()


class EventSummary(BaseModel):
    key: int = Field(default=0, ge=0)
    paste: int = Field(default=0, ge=0)
    delete: int = Field(default=0, ge=0)
    run: int = Field(default=0, ge=0)


class ClassifyRequest(BaseModel):
    events: list[SubmissionEvent] = Field(default_factory=list)
    summary: EventSummary = Field(default_factory=EventSummary)


class ClassifyResponse(BaseModel):
    label: Literal["human", "ai_generated", "assisted"] = "human"
    confidence: float = Field(default=0.55, ge=0.0, le=1.0)