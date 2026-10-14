"""Step 4 of the pipeline: aggregate skills into a monthly time series.

Input:  data/processed/posting_skills.parquet
        data/processed/clean_postings.parquet   (for the monthly denominator)
Output: data/processed/monthly_demand.parquet
        data/processed/monthly_totals.parquet

THE KEY DECISION: demand is measured as a PERCENTAGE of that month's
postings, not as a raw count.

Why it matters here specifically: this corpus has 3,682 postings in
Jan 2023 and only 449 in Sep 2024 -- the scraper had problems, not the
job market. Raw counts would show every skill "collapsing" in late 2024.
Percentages are immune to that, because the denominator moves with the
numerator.

We keep the raw counts too, so the API can report how much data sits
behind each percentage. A 40% reading from 449 postings deserves less
trust than 40% from 3,682, and the dashboard says so.
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SKILLS_FILE = ROOT / "data" / "processed" / "posting_skills.parquet"
POSTINGS_FILE = ROOT / "data" / "processed" / "clean_postings.parquet"
OUT_DEMAND = ROOT / "data" / "processed" / "monthly_demand.parquet"
OUT_TOTALS = ROOT / "data" / "processed" / "monthly_totals.parquet"
OUT_CATEGORY = ROOT / "data" / "processed" / "category_monthly.parquet"

# ---------------------------------------------------------------------
# MONTH QUALITY GATE
#
# Two independent ways a month can be untrustworthy:
#
# 1. TOO FEW POSTINGS -> noisy percentages. Sep 2024 has 272 postings;
#    a single unusual employer moves the number by 0.4 points.
#
# 2. TRUNCATED DESCRIPTIONS -> the killer, and easy to miss. From late
#    2024 the scraper began capturing roughly half-length descriptions
#    (median ~1,600 chars vs ~3,000 before). Shorter text means fewer
#    skills found, so EVERY skill's percentage falls at once. Before
#    this gate existed, the trend report showed 29 skills "declining"
#    and only 2 rising -- which was measuring the scraper, not the
#    job market.
#
# Months failing either test are excluded from trends and forecasting,
# but still written to the output and still shown in the dashboard,
# marked as low quality. We exclude them from conclusions, not from view.
# ---------------------------------------------------------------------
MIN_POSTINGS = 1_000
MIN_MEDIAN_DESC_CHARS = 2_000


def main() -> None:
    for path in (SKILLS_FILE, POSTINGS_FILE):
        if not path.exists():
            raise SystemExit(f"Missing {path}. Run the earlier scripts first.")

    skills = pd.read_parquet(SKILLS_FILE)
    postings = pd.read_parquet(
        POSTINGS_FILE, columns=["job_id", "month", "description_clean"]
    )
    postings["desc_chars"] = postings["description_clean"].str.len()

    # ---- Denominator: how many postings existed in each month ---------
    totals = (
        postings.groupby("month", as_index=False)
        .agg(
            n_postings=("job_id", "nunique"),
            median_desc_chars=("desc_chars", "median"),
        )
        .sort_values("month")
    )
    totals["median_desc_chars"] = totals["median_desc_chars"].astype(int)

    totals["is_low_volume"] = totals["n_postings"] < MIN_POSTINGS
    totals["is_truncated"] = totals["median_desc_chars"] < MIN_MEDIAN_DESC_CHARS
    totals["is_analysis_grade"] = ~(totals["is_low_volume"] | totals["is_truncated"])
    totals.to_parquet(OUT_TOTALS, index=False)

    # ---- Numerator: postings per month mentioning each skill ----------
    # nunique() not size(): a posting that says "SQL" five times still
    # counts once. We are measuring how many EMPLOYERS asked for a skill,
    # not how often the word appears.
    demand = (
        skills.groupby(["month", "skill", "category"], as_index=False)["job_id"]
        .nunique()
        .rename(columns={"job_id": "n_with_skill"})
    )

    demand = demand.merge(
        totals[["month", "n_postings", "is_low_volume", "is_analysis_grade"]], on="month"
    )
    demand["demand_pct"] = demand["n_with_skill"] / demand["n_postings"] * 100

    # ---- Fill genuine zeros -------------------------------------------
    # If a skill is absent from a month, that is a real 0% observation and
    # the time series needs it -- otherwise a gap looks like missing data
    # to the forecaster. We only fill months that exist in the data;
    # Aug 2024 has no postings at all and stays genuinely absent.
    all_skills = skills[["skill", "category"]].drop_duplicates()
    grid = totals[
        ["month", "n_postings", "is_low_volume", "is_analysis_grade"]
    ].merge(all_skills, how="cross")

    demand = grid.merge(
        demand[["month", "skill", "n_with_skill", "demand_pct"]],
        on=["month", "skill"],
        how="left",
    )
    demand["n_with_skill"] = demand["n_with_skill"].fillna(0).astype(int)
    demand["demand_pct"] = demand["demand_pct"].fillna(0.0)

    demand = demand[
        ["month", "skill", "category", "n_with_skill", "n_postings",
         "demand_pct", "is_low_volume", "is_analysis_grade"]
    ].sort_values(["skill", "month"]).reset_index(drop=True)

    demand.to_parquet(OUT_DEMAND, index=False)

    # ---- Category level ------------------------------------------------
    # Must be computed from the raw posting x skill rows, NOT by summing
    # skill counts: a posting naming both Python and SQL would be counted
    # twice and the category could exceed 100% of postings.
    category = (
        skills.groupby(["month", "category"], as_index=False)["job_id"]
        .nunique()
        .rename(columns={"job_id": "n_with_category"})
        .merge(
            totals[["month", "n_postings", "is_low_volume", "is_analysis_grade"]],
            on="month",
        )
    )
    category["coverage_pct"] = category["n_with_category"] / category["n_postings"] * 100
    category.to_parquet(OUT_CATEGORY, index=False)
    assert category["coverage_pct"].between(0, 100).all(), "category coverage > 100%!"

    # ---- Report --------------------------------------------------------
    print("=" * 68)
    print("MONTHLY AGGREGATION REPORT")
    print("=" * 68)
    print(f"\nMonths            {totals['month'].nunique()}")
    print(f"Skills            {demand['skill'].nunique()}")
    print(f"Rows (skill x month) {len(demand):,}")
    print(f"Date range        {totals['month'].min().date()} -> "
          f"{totals['month'].max().date()}")

    bad = totals[~totals["is_analysis_grade"]]
    good = totals[totals["is_analysis_grade"]]
    print(f"\nAnalysis-grade months: {len(good)}  "
          f"({good['month'].min():%Y-%m} -> {good['month'].max():%Y-%m})")
    print(f"Excluded months:       {len(bad)}")
    for _, row in bad.iterrows():
        reasons = []
        if row["is_low_volume"]:
            reasons.append(f"only {row['n_postings']:,} postings")
        if row["is_truncated"]:
            reasons.append(f"truncated descriptions ({row['median_desc_chars']:,} chars)")
        print(f"  {row['month']:%Y-%m}   {' + '.join(reasons)}")

    if len(good) < 18:
        print(f"\n  WARNING: only {len(good)} analysis-grade months. The Data Gate "
              f"wants >= 18 for defensible forecasting.")

    # Sanity: percentages must be within 0-100
    assert demand["demand_pct"].between(0, 100).all(), "demand_pct out of range!"
    print("\nSanity check: all demand_pct values within 0-100  OK")

    # ---- Spot-check one skill by hand ----------------------------------
    print("\n" + "-" * 68)
    print("SPOT CHECK -- Python, month by month")
    print("-" * 68)
    py = demand[demand["skill"] == "Python"].sort_values("month")
    for _, r in py.iterrows():
        bar = "#" * int(r["demand_pct"] / 1.2)
        flag = "" if r["is_analysis_grade"] else "  <- excluded"
        print(f"  {r['month']:%Y-%m}  {r['n_with_skill']:>5,}/{r['n_postings']:>5,}  "
              f"{r['demand_pct']:5.1f}%  {bar}{flag}")

    print(f"\nWrote {OUT_CATEGORY.relative_to(ROOT)}")
    print(f"Wrote {OUT_DEMAND.relative_to(ROOT)}")
    print(f"Wrote {OUT_TOTALS.relative_to(ROOT)}\n")


if __name__ == "__main__":
    main()
