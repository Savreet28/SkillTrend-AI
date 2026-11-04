"""Step 10: turn the raw skill graph into usable relations.

Input:  data/processed/skill_graph.parquet   (from 09)
        skills/substitutes.yaml              (curated families)
        data/processed/skill_trends.parquet  (demand + direction)
Output: data/processed/skill_relations.parquet   per-pair, labelled
        data/processed/skill_families.json       families + ranked members

TWO SOURCES OF TRUTH, EACH DOING WHAT IT IS GOOD AT
  * Whether two tools are ALTERNATIVES is declared in substitutes.yaml.
    09_cooccurrence.py proved the data cannot determine this -- known
    substitutes and known complements were statistically identical.
  * WHICH alternative to pick, and WHAT IS MISSING from a stack, come
    entirely from the data.

The ranking inside a family uses four measured signals, combined into a
single score so the UI can say "keep this one" and show its working:

  demand   current share of postings          (how many jobs want it)
  trend    recent vs previous period          (where it is going)
  reach    mean P(skill | each other skill)   (how often it travels with
                                               the rest of a stack)
  risk     volatility, as a penalty           (how trustworthy the signal)
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
GRAPH_FILE = ROOT / "data" / "processed" / "skill_graph.parquet"
TRENDS_FILE = ROOT / "data" / "processed" / "skill_trends.parquet"
FAMILIES_FILE = ROOT / "skills" / "substitutes.yaml"
OUT_RELATIONS = ROOT / "data" / "processed" / "skill_relations.parquet"
OUT_FAMILIES = ROOT / "data" / "processed" / "skill_families.json"

# Validated in 09: at this similarity, complements were identified 6/6 and
# unrelated pairs 3/3. It is only ever used to find COMPLEMENTS now --
# substitutes come from the YAML.
COMPLEMENT_SIMILARITY = 0.80

# TWO DEMAND SIGNALS, DELIBERATELY
#
# Ranking on the historical corpus alone produced bad advice: it said
# "learn Oracle", "learn SAS", "learn Informatica". Those are correct
# ABOUT THAT CORPUS -- 2022-24 data-analyst postings, which skew to
# legacy enterprise tooling -- and wrong as guidance for someone starting
# now. The live multi-role feed is small but CURRENT, so it corrects the
# bias. Both are scored, and where they disagree we say so, because the
# disagreement is itself the useful signal.
W_DEMAND_HIST = 0.28
W_DEMAND_LIVE = 0.32
W_TREND = 0.22
W_REACH = 0.13
W_RISK = 0.05

LIVE_SKILLS = ROOT / "data" / "live" / "live_skills.parquet"
LIVE_STATS = ROOT / "data" / "processed" / "role_stats.json"
# Ranks this far apart between the two corpora count as a disagreement.
DISAGREEMENT_RANKS = 2


def normalise(series: pd.Series) -> pd.Series:
    """Scale to 0-1 so signals in different units can be combined."""
    lo, hi = series.min(), series.max()
    if hi == lo:
        return pd.Series(0.5, index=series.index)
    return (series - lo) / (hi - lo)


def main() -> None:
    for path in (GRAPH_FILE, TRENDS_FILE, FAMILIES_FILE):
        if not path.exists():
            raise SystemExit(f"Missing {path}. Run 09_cooccurrence.py first.")

    graph = pd.read_parquet(GRAPH_FILE)
    trends = pd.read_parquet(TRENDS_FILE).set_index("skill")
    config = yaml.safe_load(FAMILIES_FILE.read_text())

    # Current demand from the live feed. Optional: without it the ranking
    # still works, it just falls back to history only and says so.
    live_pct: dict[str, float] = {}
    if LIVE_SKILLS.exists() and LIVE_STATS.exists():
        live = pd.read_parquet(LIVE_SKILLS)
        n_live = json.loads(LIVE_STATS.read_text())["tech_postings"]
        live_pct = (
            live.groupby("skill")["job_id"].nunique() / n_live * 100
        ).to_dict()
        print(f"\nLive signal        {len(live_pct)} skills "
              f"over {n_live:,} current postings")
    else:
        print("\nLive signal        NOT AVAILABLE — ranking on history alone")

    families: dict[str, dict] = config["families"]
    never_substitutes = {
        tuple(sorted(entry["pair"])): entry["reason"]
        for entry in config.get("not_substitutes", [])
    }

    print("=" * 70)
    print("SKILL RELATIONS")
    print("=" * 70)
    print(f"\nPairs in graph     {len(graph):,}")
    print(f"Curated families   {len(families)}")
    print(f"Explicit non-subs  {len(never_substitutes)}")

    # ---- Label every pair ----------------------------------------------
    family_of: dict[str, str] = {}
    for name, spec in families.items():
        for skill in spec["skills"]:
            family_of[skill] = name

    def label(row) -> str:
        a, b = row["skill_a"], row["skill_b"]
        key = tuple(sorted((a, b)))

        # Explicit override wins over everything.
        if key in never_substitutes:
            return "complement"

        # Same curated family -> alternatives.
        fam_a, fam_b = family_of.get(a), family_of.get(b)
        if fam_a is not None and fam_a == fam_b:
            return "substitute"

        # Otherwise let the data decide whether they travel together.
        return "complement" if row["similarity"] >= COMPLEMENT_SIMILARITY else "unrelated"

    graph["relation"] = graph.apply(label, axis=1)
    graph["family"] = graph.apply(
        lambda r: family_of.get(r["skill_a"])
        if family_of.get(r["skill_a"]) == family_of.get(r["skill_b"]) else None,
        axis=1,
    )
    graph["explicit_override"] = graph.apply(
        lambda r: never_substitutes.get(tuple(sorted((r["skill_a"], r["skill_b"])))),
        axis=1,
    )
    graph.to_parquet(OUT_RELATIONS, index=False)

    counts = graph["relation"].value_counts()
    print("\nPairs by relation:")
    for rel in ("substitute", "complement", "unrelated"):
        print(f"  {rel:<12} {counts.get(rel, 0):>6,}")

    # ---- Rank the members of each family --------------------------------
    # "reach" = how often this skill appears alongside an arbitrary other
    # skill. A high-reach tool slots into more stacks.
    reach = (
        pd.concat([
            graph.groupby("skill_a")["p_b_given_a"].mean(),
            graph.groupby("skill_b")["p_a_given_b"].mean(),
        ])
        .groupby(level=0).mean()
    )

    known = set(graph["skill_a"]) | set(graph["skill_b"])
    out_families: dict[str, dict] = {}

    for name, spec in families.items():
        members = [s for s in spec["skills"] if s in known and s in trends.index]
        if len(members) < 2:
            print(f"\n  skipping '{name}': only {len(members)} member(s) in the data")
            continue

        frame = pd.DataFrame({
            "skill": members,
            "demand_pct": [float(trends.loc[s, "overall_pct"]) for s in members],
            "live_pct": [float(live_pct.get(s, 0.0)) for s in members],
            "recent_pct": [float(trends.loc[s, "recent_pct"]) for s in members],
            "change_pts": [float(trends.loc[s, "change_pts"]) for s in members],
            "direction": [str(trends.loc[s, "direction"]) for s in members],
            "volatility": [float(trends.loc[s, "volatility"]) for s in members],
            "reach": [float(reach.get(s, 0.0)) for s in members],
        })

        live_weight = W_DEMAND_LIVE if live_pct else 0.0
        hist_weight = W_DEMAND_HIST + (0.0 if live_pct else W_DEMAND_LIVE)

        frame["score"] = (
            hist_weight * normalise(frame["demand_pct"])
            + live_weight * normalise(frame["live_pct"])
            + W_TREND * normalise(frame["change_pts"])
            + W_REACH * normalise(frame["reach"])
            - W_RISK * normalise(frame["volatility"])
        ).round(4)

        # Where the two corpora rank members differently, flag it. A tool
        # that led in 2022-24 but is absent from current postings is the
        # single most useful thing this table can tell someone.
        frame["rank_hist"] = frame["demand_pct"].rank(ascending=False).astype(int)
        frame["rank_live"] = frame["live_pct"].rank(ascending=False).astype(int)
        frame["disagreement"] = (frame["rank_hist"] - frame["rank_live"]).abs()

        # Deterministic tiebreak: live demand, then reach. Without this a
        # tie (TensorFlow vs PyTorch both scored 0.450) resolved by row order.
        frame = frame.sort_values(
            ["score", "live_pct", "reach"], ascending=False
        ).reset_index(drop=True)
        winner = frame.iloc[0]

        flagged = frame[frame["disagreement"] >= DISAGREEMENT_RANKS]
        warnings = [
            f"{r['skill']} ranks #{r['rank_hist']} in the 2022-24 corpus but "
            f"#{r['rank_live']} in current postings "
            f"({r['demand_pct']:.1f}% then, {r['live_pct']:.1f}% now)"
            for _, r in flagged.iterrows()
        ]

        out_families[name] = {
            "reason": spec["reason"].strip(),
            "recommended": winner["skill"],
            "members": frame.to_dict(orient="records"),
            "warnings": warnings,
            "rationale": (
                f"{winner['skill']}: {winner['demand_pct']:.1f}% of 2022-24 postings, "
                f"{winner['live_pct']:.1f}% of current postings, {winner['direction']}"
                + (f" ({winner['change_pts']:+.2f} points)"
                   if winner["direction"] != "stable" else "")
                + "."
            ),
        }

    OUT_FAMILIES.write_text(json.dumps({
        "complement_similarity_threshold": COMPLEMENT_SIMILARITY,
        "weights": {
            "demand_historical": W_DEMAND_HIST,
            "demand_live": W_DEMAND_LIVE,
            "trend": W_TREND,
            "reach": W_REACH,
            "risk_penalty": W_RISK,
        },
        "live_signal_used": bool(live_pct),
        "caveat": (
            "Historical demand is 2022-24 data-analyst postings; live demand is "
            "current postings across 9 tech roles, dominated by Software "
            "Engineer. A role-specific tool (a BI product, say) can score low "
            "on live purely because of that role mix, not because it is dying. "
            "Compare members WITHIN a family -- that comparison is fair, "
            "because every member faces the same role mix."
        ),
        "families": out_families,
        "never_substitutes": [
            {"pair": list(k), "reason": v} for k, v in never_substitutes.items()
        ],
    }, indent=2))

    # ---- Report -----------------------------------------------------------
    print("\n" + "-" * 70)
    print("SUBSTITUTE FAMILIES — which member to actually learn")
    print("-" * 70)
    for name, info in out_families.items():
        print(f"\n{name}  ->  learn {info['recommended']}")
        for m in info["members"]:
            mark = ">>" if m["skill"] == info["recommended"] else "  "
            print(f"  {mark} {m['skill']:<18} hist {m['demand_pct']:>5.1f}%  "
                  f"live {m['live_pct']:>5.1f}%  change {m['change_pts']:>+6.2f}p  "
                  f"score {m['score']:.3f}  [{m['direction']}]")
        for w in info["warnings"]:
            print(f"     ! {w}")

    print("\n" + "-" * 70)
    print("SAMPLE GAP LOGIC — strongest companions for a few skills")
    print("-" * 70)
    for seed in ("Python", "Tableau", "Snowflake"):
        pairs = graph[
            ((graph["skill_a"] == seed) | (graph["skill_b"] == seed))
            & (graph["relation"] == "complement")
        ].copy()
        if pairs.empty:
            continue
        pairs["other"] = pairs.apply(
            lambda r: r["skill_b"] if r["skill_a"] == seed else r["skill_a"], axis=1)
        pairs["p_other_given_seed"] = pairs.apply(
            lambda r: r["p_b_given_a"] if r["skill_a"] == seed else r["p_a_given_b"],
            axis=1)
        top = pairs.nlargest(5, "p_other_given_seed")
        print(f"\n  If you know {seed}, postings also want:")
        for _, r in top.iterrows():
            print(f"    {r['other']:<20} {r['p_other_given_seed'] * 100:>5.1f}% "
                  f"of {seed} postings")

    print(f"\n\nWrote {OUT_RELATIONS.relative_to(ROOT)}")
    print(f"Wrote {OUT_FAMILIES.relative_to(ROOT)}\n")


if __name__ == "__main__":
    main()
