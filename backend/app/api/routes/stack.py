"""The Decide endpoints: substitute families, skill relations, stack advice."""

from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app.schemas.models import (
    FamilyInfo, FamilyMember, RelatedSkill, SkillRelations, StackAnalysis,
)
from app.services.advisor import analyse_stack
from app.services.data_store import get_store

router = APIRouter(tags=["decide"])

MAX_STACK = 30


def _require_relations():
    store = get_store()
    if not store.has_relations:
        raise HTTPException(
            503,
            "Relation data unavailable. Run: python scripts/09_cooccurrence.py "
            "then python scripts/10_relations.py",
        )
    return store


@router.get("/families", response_model=list[FamilyInfo])
def list_families() -> list[FamilyInfo]:
    """Curated substitute families, each with a recommended member.

    These are curated rather than learned because 09_cooccurrence.py showed
    co-occurrence cannot distinguish substitutes from complements -- known
    examples of each were statistically identical. The RANKING inside each
    family is entirely data-driven.
    """
    store = _require_relations()

    out: list[FamilyInfo] = []
    for name, info in store.families["families"].items():
        out.append(FamilyInfo(
            family=name,
            reason=info["reason"],
            recommended=info["recommended"],
            rationale=info["rationale"],
            warnings=info.get("warnings", []),
            members=[
                FamilyMember(
                    skill=m["skill"],
                    historical_pct=round(m["demand_pct"], 2),
                    current_pct=round(m["live_pct"], 2),
                    change_pts=round(m["change_pts"], 2),
                    direction=m["direction"],
                    score=m["score"],
                    is_recommended=m["skill"] == info["recommended"],
                )
                for m in info["members"]
            ],
        ))
    return sorted(out, key=lambda f: f.family)


# Mounted at /related, NOT /skills/{skill}/related: the {skill:path}
# converter in skills.py is greedy and would swallow "Tableau/related"
# as a skill name. Skill names contain slashes (CI/CD), so :path is
# required there and this route has to live elsewhere.
@router.get("/related/{skill:path}", response_model=SkillRelations)
def related_skills(
    skill: str,
    limit: int = Query(8, ge=1, le=30),
) -> SkillRelations:
    """What this skill is an alternative to, and what it pairs with."""
    store = _require_relations()
    resolved = store.resolve_skill(skill)
    if resolved is None:
        raise HTTPException(404, f"Unknown skill: {skill!r}")

    graph = store.relations
    mine = graph[(graph["skill_a"] == resolved) | (graph["skill_b"] == resolved)].copy()
    if mine.empty:
        return SkillRelations(skill=resolved, family=None,
                              substitutes=[], complements=[])

    mine["other"] = mine.apply(
        lambda r: r["skill_b"] if r["skill_a"] == resolved else r["skill_a"], axis=1)
    mine["conditional"] = mine.apply(
        lambda r: r["p_b_given_a"] if r["skill_a"] == resolved else r["p_a_given_b"],
        axis=1)

    def rows(frame, sort_col):
        return [
            RelatedSkill(
                skill=r["other"],
                similarity=round(float(r["similarity"]), 3),
                lift=round(float(r["lift"]), 2),
                conditional_pct=round(float(r["conditional"]) * 100, 1),
                # pandas uses NaN for missing, and bool(nan) is True --
                # a plain truthiness check lets NaN through and Pydantic
                # then rejects it as a non-string.
                note=(None if pd.isna(r["explicit_override"])
                      else str(r["explicit_override"])),
            )
            for _, r in frame.nlargest(limit, sort_col).iterrows()
        ]

    family = None
    for name, info in store.families["families"].items():
        if any(m["skill"] == resolved for m in info["members"]):
            family = name
            break

    return SkillRelations(
        skill=resolved,
        family=family,
        substitutes=rows(mine[mine["relation"] == "substitute"], "similarity"),
        complements=rows(mine[mine["relation"] == "complement"], "conditional"),
    )


@router.post("/stack/analyse", response_model=StackAnalysis)
def analyse(skills: list[str]) -> StackAnalysis:
    """Given a stack, say what to drop, keep and add.

    Post a JSON array of skill names, e.g. ["Python", "Tableau", "Power BI"].
    """
    _require_relations()
    if not skills:
        raise HTTPException(400, "Send at least one skill")
    if len(skills) > MAX_STACK:
        raise HTTPException(400, f"At most {MAX_STACK} skills")

    return StackAnalysis(**analyse_stack(skills))
