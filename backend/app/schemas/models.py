"""Pydantic response models.

These do three jobs at once:
  1. document the API (FastAPI turns them into the OpenAPI schema at /docs)
  2. validate what we send, so a bug produces an error here rather than a
     confusing crash in the React app
  3. give the frontend a stable contract to code against
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class Health(BaseModel):
    status: str
    service: str
    data_loaded: bool
    error: str | None = None


class DataQuality(BaseModel):
    """Why some months are excluded from every conclusion in this API."""

    total_months: int
    analysis_grade_months: int
    excluded_months: int
    analysis_start: date
    analysis_end: date
    exclusion_reason: str


class ModelQuality(BaseModel):
    """Whether the forecasting model is actually any good."""

    skills_modelled: int
    skills_beating_baseline: int
    pct_beating_baseline: float
    mean_prophet_mae: float
    mean_naive_mae: float
    prophet_better_overall: bool
    verdict: str


class SkillSummary(BaseModel):
    skill: str
    category: str
    overall_pct: float = Field(description="Mean % of postings across analysis months")
    recent_pct: float | None = None
    previous_pct: float | None = None
    latest_pct: float | None = None
    change_pts: float | None = None
    change_rel_pct: float | None = None
    direction: str
    volatility: float
    total_mentions: int
    peak_pct: float


class CategoryInfo(BaseModel):
    category: str
    skill_count: int
    postings_pct: float = Field(description="% of postings mentioning any skill here")


class MonthPoint(BaseModel):
    month: date
    demand_pct: float
    n_with_skill: int
    n_postings: int
    rolling_3m: float | None = None
    mom_change_pts: float | None = None
    is_analysis_grade: bool


class SkillTrend(BaseModel):
    skill: str
    category: str
    points: list[MonthPoint]


class ForecastPoint(BaseModel):
    month: date
    actual: float | None = None
    yhat: float
    yhat_lower: float
    yhat_upper: float
    is_forecast: bool


class ForecastMetrics(BaseModel):
    prophet_mae: float
    prophet_mape: float | None = None
    naive_mae: float
    naive_mape: float | None = None
    beats_baseline: bool
    improvement_pct: float | None = None
    n_observations: int


class SkillForecast(BaseModel):
    skill: str
    category: str
    horizon_months: int
    points: list[ForecastPoint]
    metrics: ForecastMetrics
    caveat: str


class Summary(BaseModel):
    total_postings: int
    skills_tracked: int
    categories: int
    date_range_start: date
    date_range_end: date
    extraction_hit_rate_pct: float
    baseline_hit_rate_pct: float
    data_quality: DataQuality
    model_quality: ModelQuality | None = None
    top_skills: list[SkillSummary]
    rising_skills: list[SkillSummary]
    declining_skills: list[SkillSummary]
