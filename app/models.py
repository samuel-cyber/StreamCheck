from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import Column, DateTime, Index, String
from sqlmodel import Field, SQLModel


class ObservationStatus(str, Enum):  # noqa: UP042 — str-mixin keeps .value ergonomic
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class Observation(SQLModel, table=True):
    __tablename__ = "observation"
    __table_args__ = (
        # The two real access patterns: review-queue queries filter by status
        # and order by recency; dedupe/audit lookups hit fhir_id.
        Index("ix_observation_status_created", "status", "created_at"),
        Index("ix_observation_fhir_id", "fhir_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    photo_key: str = Field(default="", description="Object-storage key or local filename")
    text_description: str = Field(max_length=2000)
    ai_indicators: str = Field(default="[]", max_length=2000)  # JSON-encoded list[str]
    ai_confidence: float = Field(default=0.0)
    ai_reasoning: str = Field(default="", max_length=4000)
    status: ObservationStatus = Field(
        default=ObservationStatus.pending,
        sa_column=Column(String(16), nullable=False, server_default="pending"),
    )
    fhir_id: str | None = Field(default=None, max_length=64)
    reviewed_by: str | None = Field(default=None, max_length=120)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
