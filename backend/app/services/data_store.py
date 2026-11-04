"""Loads the pipeline's output once, at startup, and answers queries from memory.

WHY THIS EXISTS
The pipeline (scripts/01..06) is slow: it reads 276 MB of CSV, tokenises
58,000 documents and fits 88 Prophet models. None of that can happen
inside an HTTP request.

So the pipeline runs offline and writes Parquet. This module reads those
files once when the server boots and holds them as DataFrames. After
that every endpoint is a pandas filter -- microseconds, not minutes.

That split (train offline, serve online) is how real ML products work.
"""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache

import pandas as pd

from app.core import config


class DataStore:
    """In-memory view of the pipeline output."""

    def __init__(self) -> None:
        self.loaded = False
        self.load_error: str | None = None

        self.monthly = pd.DataFrame()
        self.totals = pd.DataFrame()
        self.skills = pd.DataFrame()
        self.categories = pd.DataFrame()
        self.forecasts = pd.DataFrame()
        self.role_profiles = pd.DataFrame()
        self.role_monthly = pd.DataFrame()
        self.role_stats: dict = {}
        self.relations = pd.DataFrame()
        self.families: dict = {}
        self.metrics: dict = {}
        self.extraction: dict = {}

        try:
            self._load()
            self.loaded = True
        except Exception as exc:                      # noqa: BLE001
            # A missing file must not crash the server -- /api/health should
            # still come up and tell you what went wrong.
            self.load_error = f"{type(exc).__name__}: {exc}"

    def _load(self) -> None:
        self.monthly = pd.read_parquet(config.MONTHLY_TRENDS)
        self.totals = pd.read_parquet(config.MONTHLY_TOTALS)
        self.skills = pd.read_parquet(config.SKILL_TRENDS)
        self.categories = pd.read_parquet(config.CATEGORY_MONTHLY)
        self.metrics = json.loads(config.MODEL_METRICS.read_text())
        self.extraction = json.loads(config.EXTRACTION_STATS.read_text())

        if config.FORECASTS.exists():
            self.forecasts = pd.read_parquet(config.FORECASTS)

        # Role data is OPTIONAL. Someone who clones the repo and runs only
        # scripts 01-06 should still get a fully working dashboard; the
        # Roles page then reports that the live feed has not been run.
        if config.ROLE_PROFILES.exists():
            self.role_profiles = pd.read_parquet(config.ROLE_PROFILES)
        if config.ROLE_MONTHLY.exists():
            self.role_monthly = pd.read_parquet(config.ROLE_MONTHLY)
            self.role_monthly["month"] = pd.to_datetime(self.role_monthly["month"])
        if config.ROLE_STATS.exists():
            self.role_stats = json.loads(config.ROLE_STATS.read_text())

        # Decide engine. Also optional: without it /api/stack returns 503
        # with instructions rather than the whole API failing to start.
        if config.SKILL_RELATIONS.exists():
            self.relations = pd.read_parquet(config.SKILL_RELATIONS)
        if config.SKILL_FAMILIES.exists():
            self.families = json.loads(config.SKILL_FAMILIES.read_text())

        self.monthly["month"] = pd.to_datetime(self.monthly["month"])
        self.totals["month"] = pd.to_datetime(self.totals["month"])
        self.categories["month"] = pd.to_datetime(self.categories["month"])
        if not self.forecasts.empty:
            self.forecasts["month"] = pd.to_datetime(self.forecasts["month"])

        self.category_of = dict(zip(self.skills["skill"], self.skills["category"]))

    # ---- lookups -------------------------------------------------------

    def has_skill(self, skill: str) -> bool:
        return skill in self.category_of

    def resolve_skill(self, name: str) -> str | None:
        """Case-insensitive skill lookup, so URLs are forgiving."""
        if name in self.category_of:
            return name
        lowered = name.lower()
        for known in self.category_of:
            if known.lower() == lowered:
                return known
        return None

    @property
    def analysis_months(self) -> pd.DataFrame:
        return self.totals[self.totals["is_analysis_grade"]]

    def date_range(self) -> tuple[date, date]:
        return self.totals["month"].min().date(), self.totals["month"].max().date()

    def analysis_range(self) -> tuple[date, date]:
        m = self.analysis_months["month"]
        return m.min().date(), m.max().date()

    def total_postings(self) -> int:
        return int(self.totals["n_postings"].sum())

    def skill_series(self, skill: str, analysis_only: bool = False) -> pd.DataFrame:
        df = self.monthly[self.monthly["skill"] == skill]
        if analysis_only:
            df = df[df["is_analysis_grade"]]
        return df.sort_values("month")

    @property
    def has_relations(self) -> bool:
        return not self.relations.empty and bool(self.families)

    @property
    def has_roles(self) -> bool:
        return not self.role_profiles.empty

    def resolve_role(self, name: str) -> str | None:
        if self.role_profiles.empty:
            return None
        known = self.role_profiles["role"].unique()
        if name in known:
            return name
        lowered = name.lower()
        for role in known:
            if role.lower() == lowered:
                return role
        return None

    def forecast_for(self, skill: str) -> pd.DataFrame:
        if self.forecasts.empty:
            return self.forecasts
        return self.forecasts[self.forecasts["skill"] == skill].sort_values("month")


@lru_cache(maxsize=1)
def get_store() -> DataStore:
    """Singleton. FastAPI dependencies call this; it loads only once."""
    return DataStore()
