"""Time-series endpoints: monthly history for one or many skills."""

from __future__ import annotations

import math

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app.api.routes.skills import row_to_summary
from app.schemas.models import MonthPoint, SkillSummary, SkillTrend
from app.services.data_store import get_store

router = APIRouter(tags=["trends"])


def _point(row: pd.Series) -> MonthPoint:
    def opt(v):
        return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), 3)

    return MonthPoint(
        month=row["month"].date(),
        demand_pct=round(float(row["demand_pct"]), 3),
        n_with_skill=int(row["n_with_skill"]),
        n_postings=int(row["n_postings"]),
        rolling_3m=opt(row["rolling_3m"]),
        mom_change_pts=opt(row["mom_change_pts"]),
        is_analysis_grade=bool(row["is_analysis_grade"]),
    )


@router.get("/trends/top", response_model=list[SkillSummary])
def top_movers(
    direction: str = Query("rising", description="rising | declining"),
    limit: int = Query(10, ge=1, le=50),
) -> list[SkillSummary]:
    """Skills moving fastest, in either direction.

    Note this is NOT simply the biggest percentage change -- 05_trends.py
    requires a move to clear both an absolute and a relative floor, and
    the skill to have enough mentions to support the claim at all.
    """
    if direction not in {"rising", "declining"}:
        raise HTTPException(400, "direction must be 'rising' or 'declining'")

    df = get_store().skills
    df = df[df["direction"] == direction]
    df = df.nlargest(limit, "change_pts") if direction == "rising" \
        else df.nsmallest(limit, "change_pts")

    return [row_to_summary(r) for _, r in df.iterrows()]


@router.get("/trends", response_model=list[SkillTrend])
def get_trends(
    skills: str = Query(..., description="Comma-separated skill names, e.g. Python,SQL"),
    analysis_only: bool = Query(
        False,
        description="Drop months the data-quality gate excluded",
    ),
) -> list[SkillTrend]:
    """Monthly series for one or more skills.

    Accepting several skills in one call is what makes the comparison
    page possible without a separate endpoint.
    """
    store = get_store()
    names = [s.strip() for s in skills.split(",") if s.strip()]
    if not names:
        raise HTTPException(400, "No skills requested")
    if len(names) > 8:
        raise HTTPException(400, "At most 8 skills per request")

    out: list[SkillTrend] = []
    for name in names:
        resolved = store.resolve_skill(name)
        if resolved is None:
            raise HTTPException(404, f"Unknown skill: {name!r}")

        series = store.skill_series(resolved, analysis_only=analysis_only)
        out.append(
            SkillTrend(
                skill=resolved,
                category=store.category_of[resolved],
                points=[_point(r) for _, r in series.iterrows()],
            )
        )
    return out
