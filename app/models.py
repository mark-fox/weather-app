from datetime import datetime, date
from typing import Optional
from sqlmodel import SQLModel, Field, Relationship

class SearchQuery(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    input_text: str
    resolved_name: str
    lat: float
    lon: float
    date_start: Optional[date] = None
    date_end: Optional[date] = None
    label: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    snapshots: list["WeatherSnapshot"] = Relationship(
        back_populates="query",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

class WeatherSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    query_id: int = Field(foreign_key="searchquery.id")
    current_json: str
    forecast_json: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    query: Optional[SearchQuery] = Relationship(back_populates="snapshots")