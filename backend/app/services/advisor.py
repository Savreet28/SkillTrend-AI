"""The Decide engine: given a stack, say what to drop, keep and add.

Four questions, answered in order:

  1. REDUNDANT   Do you have several tools that do the same job?
                 -> curated families (skills/substitutes.yaml)
  2. KEEP WHICH  Within each of those, which one is worth the time?
                 -> measured: historical demand, current demand, trend, reach
  3. MISSING     What do employers who want your stack also want?
                 -> co-occurrence: P(skill | your stack)
  4. DEAD WEIGHT Is anything you have on the way out?
                 -> trend direction

Every verdict carries the numbers it came from. Nothing here says
"consider learning X" without showing why.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from app.services.data_store import get_store


@dataclass
class Verdict:
    kind: str                 # redundant | missing | declining | solid
    severity: str             # high | medium | low
    headline: str
    detail: str
    skills: list[str] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)


# A gap is only worth raising if this share of postings wanting your
# stack also want the missing skill.
GAP_MIN_CONDITIONAL = 0.18
GAP_MAX_RESULTS = 8
# Below this share of all postings a skill is too niche to recommend.
GAP_MIN_SUPPORT_PCT = 0.8


def _family_lookup(store) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, info in store.families.get("families", {}).items():
        for member in info["members"]:
            out[member["skill"]] = name
    return out


def _redundancies(store, stack: list[str]) -> list[Verdict]:
    """Find families where the user holds more than one member."""
    verdicts: list[Verdict] = []
    fam_of = _family_lookup(store)

    grouped: dict[str, list[str]] = {}
    for skill in stack:
        family = fam_of.get(skill)
        if family:
            grouped.setdefault(family, []).append(skill)

    for family, held in grouped.items():
        if len(held) < 2:
            continue

        info = store.families["families"][family]
        ranked = [m for m in info["members"] if m["skill"] in held]
        ranked.sort(key=lambda m: m["score"], reverse=True)
        keep, drop = ranked[0], ranked[1:]

        verdicts.append(Verdict(
            kind="redundant",
            severity="high" if len(held) > 2 else "medium",
            headline=f"You have {len(held)} tools that do the same job: "
                     f"{', '.join(held)}",
            detail=(
                f"{info['reason']} Keep {keep['skill']}: "
                f"{keep['demand_pct']:.1f}% of historical postings, "
                f"{keep['live_pct']:.1f}% of current ones, {keep['direction']}. "
                f"Dropping {', '.join(d['skill'] for d in drop)} frees up time "
                f"without costing you coverage."
            ),
            skills=held,
            evidence=[
                {
                    "skill": m["skill"],
                    "verdict": "keep" if m is keep else "drop",
                    "historical_pct": round(m["demand_pct"], 2),
                    "current_pct": round(m["live_pct"], 2),
                    "change_pts": round(m["change_pts"], 2),
                    "direction": m["direction"],
                    "score": m["score"],
                }
                for m in ranked
            ],
        ))

    return sorted(verdicts, key=lambda v: len(v.skills), reverse=True)


def _gaps(store, stack: list[str]) -> list[Verdict]:
    """Skills that employers wanting this stack also ask for."""
    graph = store.relations
    if graph.empty or not stack:
        return []

    held = set(stack)
    rows = []

    for skill in stack:
        a = graph[graph["skill_a"] == skill][["skill_b", "p_b_given_a", "relation"]]
        a.columns = ["other", "conditional", "relation"]
        b = graph[graph["skill_b"] == skill][["skill_a", "p_a_given_b", "relation"]]
        b.columns = ["other", "conditional", "relation"]
        pair = pd.concat([a, b])
        # Exclude substitutes only. Requiring relation == "complement" was
        # far too strict -- that needs similarity >= 0.80, and a skill
        # appearing in 30% of postings alongside your stack is a genuine
        # gap whether or not its wider context resembles yours.
        pair = pair[pair["relation"] != "substitute"]
        pair["via"] = skill
        rows.append(pair)

    if not rows:
        return []

    candidates = pd.concat(rows)
    candidates = candidates[~candidates["other"].isin(held)]
    if candidates.empty:
        return []

    # Attribute each candidate to the stack skill that ACTUALLY produced
    # its highest conditional, not to an arbitrary slice of the stack.
    candidates = candidates.sort_values("conditional", ascending=False)
    best = candidates.drop_duplicates("other", keep="first")
    agg = (
        candidates.groupby("other")
        .agg(links=("via", "nunique"))
        .reset_index()
        .merge(best[["other", "conditional", "via"]], on="other")
    )
    agg["via"] = agg["via"].map(lambda v: [v])

    trends = store.skills.set_index("skill")
    agg = agg[agg["other"].isin(trends.index)]
    agg["support_pct"] = agg["other"].map(trends["overall_pct"])
    agg["direction"] = agg["other"].map(trends["direction"])
    agg["change_pts"] = agg["other"].map(trends["change_pts"])

    agg = agg[
        (agg["conditional"] >= GAP_MIN_CONDITIONAL)
        & (agg["support_pct"] >= GAP_MIN_SUPPORT_PCT)
    ]
    if agg.empty:
        return []

    # Rank by how often it appears with your stack, boosted if it is rising.
    agg["priority"] = agg["conditional"] * (1 + 0.5 * (agg["direction"] == "rising"))

    # Never suggest several members of one family -- they are alternatives,
    # so recommending Looker AND Tableau AND Power BI would tell the user to
    # make exactly the mistake this page exists to prevent. Keep the one the
    # family ranking already picked, else the strongest candidate.
    fam_of = _family_lookup(store)
    agg["family"] = agg["other"].map(fam_of)
    preferred = {
        name: info["recommended"]
        for name, info in store.families.get("families", {}).items()
    }
    agg["is_preferred"] = agg.apply(
        lambda r: r["family"] is None or preferred.get(r["family"]) == r["other"],
        axis=1,
    )
    agg = agg.sort_values(["is_preferred", "priority"], ascending=False)
    agg = pd.concat([
        agg[agg["family"].isna()],
        agg[agg["family"].notna()].drop_duplicates("family", keep="first"),
    ])

    agg = agg.nlargest(GAP_MAX_RESULTS, "priority")

    evidence = [
        {
            "skill": r["other"],
            "conditional_pct": round(float(r["conditional"]) * 100, 1),
            "appears_with": r["via"],
            "also_pairs_with": int(r["links"]),
            "overall_pct": round(float(r["support_pct"]), 2),
            "direction": r["direction"],
            "change_pts": round(float(r["change_pts"]), 2),
        }
        for _, r in agg.iterrows()
    ]
    top = evidence[0]

    return [Verdict(
        kind="missing",
        severity="high" if top["conditional_pct"] >= 40 else "medium",
        headline=f"{len(evidence)} skills commonly paired with your stack are missing",
        detail=(
            f"Strongest is {top['skill']}: it appears in "
            f"{top['conditional_pct']:.0f}% of postings that want "
            f"{', '.join(top['appears_with'])}"
            + (f", and it is rising ({top['change_pts']:+.2f} points)."
               if top["direction"] == "rising" else ".")
        ),
        skills=[e["skill"] for e in evidence],
        evidence=evidence,
    )]


def _declining(store, stack: list[str]) -> list[Verdict]:
    trends = store.skills.set_index("skill")
    held = [s for s in stack if s in trends.index]

    falling = [
        {
            "skill": s,
            "overall_pct": round(float(trends.loc[s, "overall_pct"]), 2),
            "change_pts": round(float(trends.loc[s, "change_pts"]), 2),
            "direction": trends.loc[s, "direction"],
        }
        for s in held
        if trends.loc[s, "direction"] == "declining"
    ]
    if not falling:
        return []

    falling.sort(key=lambda d: d["change_pts"])
    worst = falling[0]

    return [Verdict(
        kind="declining",
        severity="medium",
        headline=f"{len(falling)} skill(s) in your stack are declining",
        detail=(
            f"{worst['skill']} fell {abs(worst['change_pts']):.2f} points "
            f"between the comparison windows. Declining does not mean useless "
            f"— it still appears in {worst['overall_pct']:.1f}% of postings — "
            f"but it is a poor choice to START learning now."
        ),
        skills=[d["skill"] for d in falling],
        evidence=falling,
    )]


def analyse_stack(stack: list[str]) -> dict:
    """Run every check and assemble the response."""
    store = get_store()

    resolved, unknown = [], []
    for raw in stack:
        match = store.resolve_skill(raw.strip())
        (resolved if match else unknown).append(match or raw.strip())
    resolved = list(dict.fromkeys(resolved))      # de-dupe, keep order

    if not resolved:
        return {
            "stack": [], "unknown": unknown, "verdicts": [],
            "summary": "No recognised skills in that stack.",
            "caveat": store.families.get("caveat", ""),
        }

    verdicts = _redundancies(store, resolved) + _gaps(store, resolved) \
        + _declining(store, resolved)

    if not verdicts:
        verdicts = [Verdict(
            kind="solid",
            severity="low",
            headline="No redundancy, no obvious gaps, nothing declining",
            detail="Your stack looks coherent against this corpus. That is a "
                   "real result, not a fallback — but remember the corpus is "
                   "data-analyst heavy, so coverage is weakest for web and "
                   "DevOps tooling.",
            skills=resolved,
        )]

    n_redundant = sum(len(v.skills) - 1 for v in verdicts if v.kind == "redundant")
    n_missing = sum(len(v.skills) for v in verdicts if v.kind == "missing")

    parts = []
    if n_redundant:
        parts.append(f"{n_redundant} tool(s) you could drop")
    if n_missing:
        parts.append(f"{n_missing} worth adding")
    summary = (
        f"{len(resolved)} skills analysed: " + ", ".join(parts) + "."
        if parts else f"{len(resolved)} skills analysed; nothing to change."
    )

    return {
        "stack": resolved,
        "unknown": unknown,
        "verdicts": [v.__dict__ for v in verdicts],
        "summary": summary,
        "caveat": store.families.get("caveat", ""),
    }
