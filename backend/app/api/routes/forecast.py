"""Forecast endpoint.

Every forecast response carries its own backtest metrics. That is
deliberate: the UI should be unable to draw a prediction without also
being handed the evidence for how much to trust it.
"""

from __future__ import annotations

import math

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app.schemas.models import ForecastMetrics, ForecastPoint, SkillForecast
from app.services.data_store import get_store
from app.services.forecast_service import forecast_skill
from app.services.upload_service import UploadError, load_upload

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


def _on_demand(skill: str, upload_id: str, horizon: int) -> SkillForecast:
    """Fit this skill live, against an uploaded dataset.

    Uploads have no precomputed forecasts and their origin is wherever the
    user's data ends, so the model is fitted per request (about a second).
    """
    store = get_store()
    resolved = store.resolve_skill(skill)
    if resolved is None:
        raise HTTPException(404, f"Unknown skill: {skill!r}")

    try:
        monthly, summary = load_upload(upload_id)
    except UploadError as exc:
        raise HTTPException(404, str(exc)) from exc

    series = monthly[monthly["skill"] == resolved][["month", "demand_pct"]]
    if series.empty:
        raise HTTPException(
            404, f"{resolved!r} does not appear in upload {upload_id}.")

    result = forecast_skill(series, resolved, horizon=horizon)

    points = [
        ForecastPoint(month=h["month"], actual=h["actual"], yhat=h["actual"],
                      yhat_lower=h["actual"], yhat_upper=h["actual"],
                      is_forecast=False)
        for h in result.history
    ] + [
        ForecastPoint(month=f["month"], actual=None, yhat=f["yhat"],
                      yhat_lower=f["yhat_lower"], yhat_upper=f["yhat_upper"],
                      is_forecast=True)
        for f in result.forecast
    ]

    metrics = ForecastMetrics(
        prophet_mae=result.prophet_mae or 0.0,
        naive_mae=result.naive_mae or 0.0,
        beats_baseline=bool(result.beats_baseline),
        n_observations=result.n_observations,
    )
    caveat = result.caveat
    if summary.get("join_month"):
        caveat += (
            f" This series splices your upload onto the historical corpus at "
            f"{summary['join_month']}; they are different populations, so a "
            f"jump at that month is a change of source, not of market."
        )

    return SkillForecast(
        skill=resolved,
        category=store.category_of[resolved],
        horizon_months=horizon,
        points=points,
        metrics=metrics,
        caveat=caveat,
    )


@router.get("/forecast/{skill:path}", response_model=SkillForecast)
def get_forecast(
    skill: str,
    dataset: str | None = Query(
        None, description="An upload_id. Omit to use the default corpus."),
    horizon: int = Query(6, ge=1, le=12),
) -> SkillForecast:
    """History plus a 6-month forecast with an 80% interval.

    Without `dataset` this serves the precomputed batch forecast (instant).
    With one, the model is fitted on demand against that upload.
    """
    store = get_store()

    if dataset:
        return _on_demand(skill, dataset, horizon)

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
