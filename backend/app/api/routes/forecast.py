"""Forecast endpoint.

Every forecast response carries its own backtest metrics. That is
deliberate: the UI should be unable to draw a prediction without also
being handed the evidence for how much to trust it.
"""

from __future__ import annotations

import math

import pandas as pd
from fastapi import APIRouter, HTTPException

from app.schemas.models import ForecastMetrics, ForecastPoint, SkillForecast
from app.services.data_store import get_store

router = APIRouter(tags=["forecast"])


def _point(row: pd.Series) -> ForecastPoint:
    actual = row["actual"]
    if actual is None or (isinstance(actual, float) and math.isnan(actual)):
        actual = None
    else:
        actual = round(float(actual), 3)

    return ForecastPoint(
        month=row["month"].date(),
        actual=actual,
        yhat=round(float(row["yhat"]), 3),
        yhat_lower=round(float(row["yhat_lower"]), 3),
        yhat_upper=round(float(row["yhat_upper"]), 3),
        is_forecast=bool(row["is_forecast"]),
    )


@router.get("/forecast/{skill:path}", response_model=SkillForecast)
def get_forecast(skill: str) -> SkillForecast:
    """History plus a 6-month Prophet forecast with an 80% interval."""
    store = get_store()

    resolved = store.resolve_skill(skill)
    if resolved is None:
        raise HTTPException(404, f"Unknown skill: {skill!r}")

    series = store.forecast_for(resolved)
    if series.empty:
        raise HTTPException(
            404,
            f"No forecast for {resolved!r}. Skills below 0.5% mean demand are "
            f"too sparse to model honestly.",
        )

    raw = store.metrics["per_skill"][resolved]
    metrics = ForecastMetrics(**raw)

    if metrics.beats_baseline:
        caveat = (
            f"Prophet beat the naive carry-forward baseline on this skill "
            f"(MAE {metrics.prophet_mae:.2f} vs {metrics.naive_mae:.2f} "
            f"percentage points on a 3-month holdout). Treat the forecast as "
            f"indicative, not precise."
        )
    else:
        caveat = (
            f"Prophet did NOT beat a naive 'next month equals last month' "
            f"baseline on this skill (MAE {metrics.prophet_mae:.2f} vs "
            f"{metrics.naive_mae:.2f}). The forecast is shown for completeness, "
            f"but carries no more information than the last observed value."
        )

    return SkillForecast(
        skill=resolved,
        category=store.category_of[resolved],
        horizon_months=store.metrics["horizon_months"],
        points=[_point(r) for _, r in series.iterrows()],
        metrics=metrics,
        caveat=caveat,
    )
