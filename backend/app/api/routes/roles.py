"""Role comparison endpoints, backed by the live job-board feed.

These are kept apart from the rest of the API on purpose. Everything
else in this service describes 58,276 US data-analyst postings from
2022-2024 (Kaggle). This describes a few thousand mostly-European,
mostly-remote postings collected this month from live job boards.

Different source, different population, different window. The two are
never combined into a single number, and every response here carries a
caveat saying so.
"""

from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app.schemas.models import (
    LiveStatus, RoleInfo, RoleMatrixCell, RoleMatrixRow, RoleSkill,
)
from app.services.data_store import get_store

router = APIRouter(tags=["roles"])

CAVEAT = (
    "Role data comes from live job-board APIs (Arbeitnow, Jobicy, Remotive) "
    "and is a different population from the historical Kaggle corpus used "
    "elsewhere in this API: mostly European and remote, collected this month. "
    "Compare roles against each other, not against the historical figures."
)


def _require_roles():
    store = get_store()
    if not store.has_roles:
        raise HTTPException(
            503,
            "Role data unavailable. Run: python scripts/07_fetch_live.py "
            "then python scripts/08_roles.py",
        )
    return store


def _skill_rows(frame: pd.DataFrame) -> list[RoleSkill]:
    return [
        RoleSkill(
            skill=r["skill"],
            category=r["category"],
            demand_pct=round(float(r["demand_pct"]), 2),
            n_with_skill=int(r["n_with_skill"]),
            lift=round(float(r["lift"]), 2),
        )
        for _, r in frame.iterrows()
    ]


@router.get("/live/status", response_model=LiveStatus)
def live_status() -> LiveStatus:
    """Is the live feed present, how fresh is it, and how much is there."""
    store = get_store()
    if not store.has_roles or not store.role_stats:
        return LiveStatus(
            available=False,
            caveat="Live feed not yet fetched. Run scripts/07_fetch_live.py.",
        )

    s = store.role_stats
    last = None
    if not store.role_monthly.empty:
        last = store.role_monthly["month"].max().to_pydatetime()

    return LiveStatus(
        available=True,
        live_postings=s["live_postings"],
        tech_postings=s["tech_postings"],
        roles=s["roles"],
        hit_rate_pct=s["hit_rate_pct"],
        months_collected=s["months_collected"],
        sources=s["sources"],
        last_fetched=last,
        caveat=CAVEAT,
    )


@router.get("/roles", response_model=list[RoleInfo])
def list_roles(
    top: int = Query(10, ge=0, le=40, description="Top skills to include per role"),
) -> list[RoleInfo]:
    """Every role family, with its most-demanded skills."""
    store = _require_roles()
    profiles = store.role_profiles

    out: list[RoleInfo] = []
    for role, group in profiles.groupby("role"):
        n = int(group["role_postings"].iloc[0])
        out.append(
            RoleInfo(
                role=role,
                n_postings=n,
                is_confident=bool(group["is_confident"].iloc[0]),
                top_skills=_skill_rows(group.nlargest(top, "demand_pct")) if top else [],
            )
        )
    return sorted(out, key=lambda r: r.n_postings, reverse=True)


@router.get("/roles/matrix", response_model=list[RoleMatrixRow])
def role_matrix(
    skills: str | None = Query(
        None, description="Comma-separated skills. Omit for the top skills overall."
    ),
    limit: int = Query(15, ge=1, le=40),
) -> list[RoleMatrixRow]:
    """Skill x role grid — the data behind the comparison table.

    This is the endpoint that answers "do software engineers use Python
    differently from data analysts?". Read ACROSS a row to compare roles.
    """
    store = _require_roles()
    profiles = store.role_profiles

    if skills:
        wanted = []
        for raw in skills.split(","):
            name = raw.strip()
            if not name:
                continue
            match = store.resolve_skill(name)
            if match is None:
                raise HTTPException(404, f"Unknown skill: {name!r}")
            wanted.append(match)
    else:
        # Rank by total reach across roles so the default grid is interesting.
        wanted = (
            profiles.groupby("skill")["demand_pct"].mean()
            .nlargest(limit).index.tolist()
        )

    roles = sorted(profiles["role"].unique())
    rows: list[RoleMatrixRow] = []

    for skill in wanted:
        sub = profiles[profiles["skill"] == skill]
        if sub.empty:
            continue
        by_role = dict(zip(sub["role"], sub["demand_pct"]))
        rows.append(
            RoleMatrixRow(
                skill=skill,
                category=sub["category"].iloc[0],
                cells=[
                    RoleMatrixCell(role=r, demand_pct=round(float(by_role.get(r, 0.0)), 2))
                    for r in roles
                ],
            )
        )
    return rows


@router.get("/roles/{role:path}", response_model=RoleInfo)
def get_role(
    role: str,
    top: int = Query(25, ge=1, le=120),
    sort: str = Query("demand_pct", description="demand_pct | lift"),
) -> RoleInfo:
    """One role's full skill profile.

    Sorting by `lift` instead of `demand_pct` shows what is DISTINCTIVE
    about the role rather than what is merely common everywhere.
    """
    store = _require_roles()
    resolved = store.resolve_role(role)
    if resolved is None:
        known = sorted(store.role_profiles["role"].unique())
        raise HTTPException(404, f"Unknown role: {role!r}. Known roles: {known}")

    group = store.role_profiles[store.role_profiles["role"] == resolved]
    key = "lift" if sort == "lift" else "demand_pct"

    return RoleInfo(
        role=resolved,
        n_postings=int(group["role_postings"].iloc[0]),
        is_confident=bool(group["is_confident"].iloc[0]),
        top_skills=_skill_rows(group.nlargest(top, key)),
    )
