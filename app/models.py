from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel, create_engine

from .config import DB_PATH


class Observation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    photo_path: str
    text_description: str
    ai_indicators: str = "[]"  # JSON-encoded list[str]
    ai_confidence: float = 0.0
    ai_reasoning: str = ""
    status: str = "pending"
    fhir_id: Optional[str] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
