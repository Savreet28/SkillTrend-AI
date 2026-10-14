"""Skill catalogue endpoints: list, search, filter, and single-skill detail."""

from __future__ import annotations

import math

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app.schemas.models import CategoryInfo, SkillSummary
from app.services.data_store import get_store

router = APIRouter(tags=["skills"])


def clean(value):
    """pandas uses NaN for missing; JSON needs null."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def row_to_summary(row: pd.Series) -> SkillSummary:
    return SkillSummary(
        skill=row["skill"],
        category=row["category"],
        overall_pct=round(float(row["overall_pct"]), 3),
        recent_pct=clean(round(float(row["recent_pct"]), 3)),
        previous_pct=clean(round(float(row["previous_pct"]), 3)),
        latest_pct=clean(round(float(row["latest_pct"]), 3)),
        change_pts=clean(round(float(row["change_pts"]), 3)),
        change_rel_pct=clean(round(float(row["change_rel_pct"]), 2)),
        direction=row["direction"],
        volatility=round(float(row["volatility"]), 3),
        total_mentions=int(row["total_mentions"]),
        peak_pct=round(float(row["peak_pct"]), 3),
    )


@router.get("/categories", response_model=list[CategoryInfo])
def list_categories() -> list[CategoryInfo]:
    """The nine skill categories, with how many postings mention each."""
    store = get_store()
    # DISTINCT postings per category, precomputed by 04_aggregate.py. Summing
    # per-skill counts here would double-count a posting naming both Python
    # and SQL, and could push a category above 100%.
    cats = store.categories[store.categories["is_analysis_grade"]]
    total = int(store.analysis_months["n_postings"].sum())

    out: list[CategoryInfo] = []
    for category, group in store.skills.groupby("category"):
        covered = int(cats[cats["category"] == category]["n_with_category"].sum())
        out.append(
            CategoryInfo(
                category=category,
                skill_count=int(len(group)),
                postings_pct=round(covered / total * 100, 2),
            )
        )
    return sorted(out, key=lambda c: c.postings_pct, reverse=True)


@router.get("/skills", response_model=list[SkillSummary])
def list_skills(
    category: str | None = Query(None, description="Filter to one category"),
    q: str | None = Query(None, description="Case-insensitive substring search"),
    direction: str | None = Query(None, description="rising | declining | stable"),
    limit: int = Query(200, ge=1, le=500),
    sort: str = Query("overall_pct", description="overall_pct | change_pts | skill"),
) -> list[SkillSummary]:
    """Searchable, filterable list of every tracked skill."""
    df = get_store().skills.copy()

    if category:
        df = df[df["category"].str.lower() == category.lower()]
    if q:
        df = df[df["skill"].str.contains(q, case=False, regex=False)]
    if direction:
        df = df[df["direction"] == direction.lower()]

    if sort == "skill":
        df = df.sort_values("skill")
    elif sort == "change_pts":
        df = df.sort_values("change_pts", ascending=False)
    else:
        df = df.sort_values("overall_pct", ascending=False)

    return [row_to_summary(r) for _, r in df.head(limit).iterrows()]


@router.get("/skills/{skill:path}", response_model=SkillSummary)
def get_skill(skill: str) -> SkillSummary:
    """One skill's summary. `:path` so names like 'CI/CD' and 'A/B Testing' work."""
    store = get_store()
    resolved = store.resolve_skill(skill)
    if resolved is None:
        raise HTTPException(status_code=404, detail=f"Unknown skill: {skill!r}")

    row = store.skills[store.skills["skill"] == resolved].iloc[0]
    return row_to_summary(row)
