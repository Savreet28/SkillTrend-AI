"""Step 8: build skill profiles for each role family from the live feed.

Input:  data/live/live_postings.parquet
Output: data/processed/role_profiles.parquet   (role x skill, cross-sectional)
        data/processed/role_monthly.parquet    (role x skill x month, grows over time)
        data/processed/role_stats.json

WHAT THIS ANSWERS
"Do software engineers use Python differently from data analysts?"
For every role we compute what share of its postings mention each skill,
so the roles can be put side by side.

WHAT IT DELIBERATELY DOES NOT DO
It does not produce role trends or role forecasts. The live feed started
in Nov 2026 and job boards only list CURRENT openings, so there is no
role history to analyse yet -- it accumulates one month at a time from
here. role_monthly.parquet exists to collect it, and will become useful
once several months have built up. Claiming a trend from one month of
data would be exactly the kind of invented result this project avoids.

WHY THE ROLE DATA IS KEPT SEPARATE FROM THE KAGGLE DATA
Different sources, different populations, different time windows. The
Kaggle corpus is 58k US data-analyst ads from 2022-2024; the live feed
is a few thousand mostly-European, mostly-remote ads from this month.
Merging them into one number would be meaningless. They are stored,
served and displayed separately throughout.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from skill_extractor import SkillExtractor  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
IN_FILE = ROOT / "data" / "live" / "live_postings.parquet"
OUT_PROFILES = ROOT / "data" / "processed" / "role_profiles.parquet"
OUT_MONTHLY = ROOT / "data" / "processed" / "role_monthly.parquet"
OUT_STATS = ROOT / "data" / "processed" / "role_stats.json"
# Cumulative per-posting skill records. This is what makes it safe for
# 07_fetch_live.py to throw away old description text: the skills were
# already extracted and stored here, so nothing is lost.
SKILLS_FILE = ROOT / "data" / "live" / "live_skills.parquet"

# A role needs at least this many postings before we report a profile.
MIN_POSTINGS_PER_ROLE = 30
# Below this, the profile is published but flagged as low confidence.
CONFIDENT_POSTINGS = 100

URL_RE = re.compile(r"https?://\S+|www\.\S+")
WHITESPACE_RE = re.compile(r"\s+")


def clean(text: str) -> str:
    """Same normalisation as 02_clean.py, so both corpora are treated alike.

    Punctuation is deliberately preserved -- stripping it would turn
    "C++" into "c" and "CI/CD" into "ci cd".
    """
    text = URL_RE.sub(" ", str(text).lower())
    return WHITESPACE_RE.sub(" ", text).strip()


def main() -> None:
    if not IN_FILE.exists():
        raise SystemExit(f"Missing {IN_FILE}. Run 07_fetch_live.py first.")

    extractor = SkillExtractor()
    live = pd.read_parquet(IN_FILE)

    print("=" * 70)
    print("ROLE SKILL PROFILES")
    print("=" * 70)
    print(f"\nLive postings stored  {len(live):,}")

    # "Other" is everything the role classifier could not place -- marketing,
    # nursing, logistics. Including it would pollute every comparison.
    tech = live[live["role"] != "Other"].copy()
    print(f"Tech-role postings    {len(tech):,} "
          f"({len(tech) / len(live) * 100:.1f}%)")

    counts = tech["role"].value_counts()
    usable_roles = counts[counts >= MIN_POSTINGS_PER_ROLE].index.tolist()
    dropped = counts[counts < MIN_POSTINGS_PER_ROLE]

    if len(dropped):
        print(f"\nRoles below {MIN_POSTINGS_PER_ROLE} postings, excluded:")
        for role, n in dropped.items():
            print(f"  {role:<28} {n:>5}")

    tech = tech[tech["role"].isin(usable_roles)]

    # ---- Extract skills ------------------------------------------------
    # Only postings that still carry description text need extracting.
    # Older ones were pruned by 07_fetch_live.py after their skills were
    # already stored in live_skills.parquet, so we reuse those.
    previous = (
        pd.read_parquet(SKILLS_FILE) if SKILLS_FILE.exists() else
        pd.DataFrame(columns=["job_id", "role", "skill", "month"])
    )
    # Postings where NO skill was found never appear in live_skills.parquet,
    # so they are re-checked on every run. That is cheap (a few hundred docs)
    # and harmless: once their description is pruned, re-extraction yields the
    # same empty result it did the first time.
    done = set(previous["job_id"])

    todo = tech[(tech["description"].str.len() > 0) & (~tech["job_id"].isin(done))]
    print(f"\nAlready extracted  {len(done):,} postings")
    print(f"Extracting skills from {len(todo):,} new postings...")

    rows: list[tuple[str, str, str, pd.Timestamp]] = []
    job_ids = todo["job_id"].tolist()
    roles = todo["role"].tolist()
    months = todo["month"].tolist()

    texts = todo["description"].map(clean)
    for i, skills in enumerate(extractor.extract_many(texts, batch_size=200)):
        for skill in skills:
            rows.append((job_ids[i], roles[i], skill, months[i]))

    found = pd.concat(
        [previous, pd.DataFrame(rows, columns=["job_id", "role", "skill", "month"])],
        ignore_index=True,
    ).drop_duplicates(["job_id", "skill"])

    # Keep only postings still present in the live file, and refresh the
    # role label in case the classifier improved since the first run.
    found = found[found["job_id"].isin(set(tech["job_id"]))]
    found["role"] = found["job_id"].map(dict(zip(tech["job_id"], tech["role"])))
    found.to_parquet(SKILLS_FILE, index=False)

    found["category"] = found["skill"].map(extractor.category_of)

    hit_rate = found["job_id"].nunique() / len(tech) * 100
    print(f"  {len(found):,} skill mentions")
    print(f"  hit rate {hit_rate:.1f}% of postings matched >= 1 skill")

    # ---- Cross-sectional profile: role x skill --------------------------
    role_totals = tech.groupby("role")["job_id"].nunique().rename("role_postings")

    profiles = (
        found.groupby(["role", "skill", "category"], as_index=False)["job_id"]
        .nunique()
        .rename(columns={"job_id": "n_with_skill"})
        .merge(role_totals, on="role")
    )
    profiles["demand_pct"] = profiles["n_with_skill"] / profiles["role_postings"] * 100
    profiles["is_confident"] = profiles["role_postings"] >= CONFIDENT_POSTINGS

    # A skill's "distinctiveness" for a role: how much more this role asks
    # for it than the average role does. This is what makes the comparison
    # interesting -- every role wants SQL, but only data roles want Tableau.
    avg = profiles.groupby("skill")["demand_pct"].mean().rename("avg_across_roles")
    profiles = profiles.merge(avg, on="skill")
    profiles["lift"] = profiles["demand_pct"] - profiles["avg_across_roles"]

    profiles = profiles.sort_values(["role", "demand_pct"], ascending=[True, False])
    profiles.to_parquet(OUT_PROFILES, index=False)

    # ---- Monthly, for the time series that builds up from here ----------
    monthly_totals = tech.groupby(["role", "month"])["job_id"].nunique().rename("role_postings")
    role_monthly = (
        found.groupby(["role", "skill", "month"], as_index=False)["job_id"]
        .nunique()
        .rename(columns={"job_id": "n_with_skill"})
        .merge(monthly_totals, on=["role", "month"])
    )
    role_monthly["demand_pct"] = (
        role_monthly["n_with_skill"] / role_monthly["role_postings"] * 100
    )
    role_monthly.to_parquet(OUT_MONTHLY, index=False)

    # ---- Report ----------------------------------------------------------
    print("\n" + "-" * 70)
    print("TOP 8 SKILLS PER ROLE")
    print("-" * 70)
    for role in sorted(usable_roles):
        sub = profiles[profiles["role"] == role].head(8)
        n = int(role_totals[role])
        flag = "" if n >= CONFIDENT_POSTINGS else "   [LOW CONFIDENCE]"
        print(f"\n{role}  ({n:,} postings){flag}")
        for _, r in sub.iterrows():
            bar = "#" * int(r["demand_pct"] / 2.5)
            print(f"   {r['skill']:<20} {r['demand_pct']:>5.1f}%  {bar}")

    # ---- The headline comparison -----------------------------------------
    print("\n" + "-" * 70)
    print("SAME SKILL, DIFFERENT ROLES  (% of that role's postings)")
    print("-" * 70)
    interesting = ["Python", "SQL", "Microsoft Excel", "Tableau", "Power BI",
                   "Docker", "Kubernetes", "AWS", "Machine Learning", "Git"]
    pivot = profiles.pivot_table(
        index="skill", columns="role", values="demand_pct", fill_value=0.0
    )
    shown = [s for s in interesting if s in pivot.index]
    cols = sorted(usable_roles)
    header = "skill".ljust(18) + "".join(c[:11].rjust(12) for c in cols)
    print(header)
    for skill in shown:
        line = skill.ljust(18)
        for c in cols:
            line += f"{pivot.loc[skill, c]:>11.1f}%"
        print(line)

    stats = {
        "live_postings": int(len(live)),
        "tech_postings": int(len(tech)),
        "roles": sorted(usable_roles),
        "role_counts": {k: int(v) for k, v in role_totals.items()},
        "hit_rate_pct": round(float(hit_rate), 2),
        "months_collected": int(tech["month"].nunique()),
        "sources": {k: int(v) for k, v in live["source"].value_counts().items()},
        "min_postings_per_role": MIN_POSTINGS_PER_ROLE,
        "confident_threshold": CONFIDENT_POSTINGS,
    }
    OUT_STATS.write_text(json.dumps(stats, indent=2))

    print(f"\n\nWrote {SKILLS_FILE.relative_to(ROOT)}")
    print(f"Wrote {OUT_PROFILES.relative_to(ROOT)}")
    print(f"Wrote {OUT_MONTHLY.relative_to(ROOT)}")
    print(f"Wrote {OUT_STATS.relative_to(ROOT)}\n")


if __name__ == "__main__":
    main()
