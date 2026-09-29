from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class SessionTitle(BaseModel):
    title: str = Field(min_length=1, max_length=120)

    # Runs before the min_length check, so "   " is rejected as blank rather
    # than accepted as three spaces.
    @field_validator("title", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class SessionCreate(SessionTitle):
    pass


class SessionUpdate(SessionTitle):
    pass


class SessionSummary(BaseModel):
    id: str
    created_at: datetime
    ended_at: datetime | None
    source_language: str | None
    target_language: str | None
    title: str | None
    message_count: int


class SessionListResponse(BaseModel):
    items: list[SessionSummary]
    has_more: bool


class MessageRecord(BaseModel):
    id: str
    sequence: int
    created_at: datetime
    original_text: str
    translated_text: str | None
    target_language: str | None


class SessionDetail(SessionSummary):
    messages: list[MessageRecord]


class TranslateRequest(BaseModel):
    target_language: str


class MessageTranslation(BaseModel):
    message_id: str
    translated_text: str | None


class TranslateResponse(BaseModel):
    target_language: str
    translations: list[MessageTranslation]
