"""The configuration stored in an AgentVersion. Validated on every write; unknown keys are rejected."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LanguageCode = Literal["en", "te", "hi", "ta", "kn", "ml", "ar", "es", "fr", "de", "pt", "ja", "ko", "zh"]
Weekday = Literal["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LanguageSettings(_Strict):
    supported: list[LanguageCode] = Field(default_factory=lambda: ["en"], min_length=1)
    default: LanguageCode = "en"
    auto_detect: bool = True

    @model_validator(mode="after")
    def default_is_supported(self) -> "LanguageSettings":
        if self.default not in self.supported:
            self.supported = [self.default, *self.supported]
        return self


class LLMSettings(_Strict):
    model: str = Field(default="gemini-2.5-flash", max_length=100)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class VoiceSettings(_Strict):
    voice: str = Field(default="Puck", max_length=60)
    live_model: str = Field(default="gemini-2.0-flash-live-001", max_length=100)


class Limits(_Strict):
    max_call_seconds: int = Field(default=300, ge=30, le=7200)


class BusinessHours(_Strict):
    timezone: str = Field(default="Asia/Kolkata", max_length=60)
    days: list[Weekday] = Field(default_factory=lambda: ["Mon", "Tue", "Wed", "Thu", "Fri"])
    start: str = Field(default="09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(default="18:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class Handoff(_Strict):
    phone: str = Field(default="", max_length=20)


class KnowledgeSettings(_Strict):
    source_ids: list[str] = Field(default_factory=list, max_length=200)


class ToolSetting(_Strict):
    key: str = Field(max_length=60)
    enabled: bool = True
    config: dict = Field(default_factory=dict)


class AgentConfig(_Strict):
    schema_version: Literal[1] = 1
    instructions: str = Field(default="", max_length=20000)
    greetings: dict[LanguageCode, str] = Field(default_factory=dict)
    languages: LanguageSettings = Field(default_factory=LanguageSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    limits: Limits = Field(default_factory=Limits)
    hours: BusinessHours = Field(default_factory=BusinessHours)
    handoff: Handoff = Field(default_factory=Handoff)
    knowledge: KnowledgeSettings = Field(default_factory=KnowledgeSettings)
    tools: list[ToolSetting] = Field(default_factory=list, max_length=50)
    workflow_id: Optional[str] = None

    @field_validator("greetings")
    @classmethod
    def greeting_length(cls, value: dict[str, str]) -> dict[str, str]:
        for lang, text in value.items():
            if len(text) > 500:
                raise ValueError(f"Greeting for '{lang}' is longer than 500 characters")
        return value
