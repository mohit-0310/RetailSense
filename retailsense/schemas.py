from __future__ import annotations

from pydantic import BaseModel, Field


class RecommendationSummary(BaseModel):
    item_id: str
    store_id: str
    state_id: str
    cat_id: str
    dept_id: str
    priority: str
    trend_label: str
    recommended_action: str
    short_reason: str
    severity_score: float


class PagedRecommendations(BaseModel):
    items: list[RecommendationSummary]
    priority: str
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_previous: bool


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    item_id: str | None = None
    store_id: str | None = None


class AskResponse(BaseModel):
    answer: str
    mode: str

