from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


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
    focus: int = Field(default=0, ge=0)


class ClassifyRequest(BaseModel):
    events: list[SubmissionEvent] = Field(default_factory=list)
    summary: EventSummary = Field(default_factory=EventSummary)
    code: str = Field(default="", max_length=50_000)


class ClassifyResponse(BaseModel):
    label: Literal["human", "ai_generated", "assisted"] = "human"
    confidence: float = Field(default=0.55, ge=0.0, le=1.0)


class GenerateProblemRequest(BaseModel):
    prompt: str = Field(min_length=10, max_length=8000)

    @field_validator("prompt", mode="before")
    @classmethod
    def normalize_prompt(cls, value):
        return str(value or "").strip()

    @field_validator("prompt")
    @classmethod
    def ensure_prompt_length(cls, value):
        if len(value) < 10:
            raise ValueError("El prompt debe tener al menos 10 caracteres.")
        return value


class VisibleTest(BaseModel):
    input_text: str = Field(min_length=1, max_length=2000)
    expected_text: str = Field(min_length=1, max_length=2000)

    @field_validator("input_text", "expected_text", mode="before")
    @classmethod
    def normalize_text(cls, value):
        return str(value or "").strip()


class GeneratedStage(BaseModel):
    stage_index: int = Field(ge=1, le=1)
    prompt_md: str = Field(min_length=3, max_length=8000)
    hidden_count: int = Field(default=0, ge=0, le=1000)
    visible_tests: list[VisibleTest] = Field(min_length=1, max_length=20)
    hidden_tests: list[VisibleTest] = Field(default_factory=list, max_length=20)


class StarterCode(BaseModel):
    python: str = Field(min_length=1, max_length=20000)
    javascript: str = Field(min_length=1, max_length=20000)
    typescript: str = Field(min_length=1, max_length=20000)

    @field_validator("python", "javascript", "typescript", mode="before")
    @classmethod
    def normalize_code(cls, value):
        return str(value or "").rstrip()


class GenerateProblemResponse(BaseModel):
    title: str = Field(min_length=3, max_length=140)
    difficulty: Literal[1, 2, 3] = 2
    tags: list[str] = Field(default_factory=list)
    statement_md: str = Field(min_length=10, max_length=40000)
    starter_code: StarterCode
    stages: list[GeneratedStage] = Field(min_length=1, max_length=1)
