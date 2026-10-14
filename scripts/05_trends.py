"""Step 5 of the pipeline: turn monthly demand into trends.

Input:  data/processed/monthly_demand.parquet
Output: data/processed/monthly_trends.parquet  (month level, + rolling avg & MoM)
        data/processed/skill_trends.parquet    (one summary row per skill)

Three guards against reporting noise as a finding:

1. A RELATIVE floor AND an ABSOLUTE floor before calling anything a
   trend. A skill going 0.1% -> 0.2% is "+100%", which is meaningless.
   A skill needs to move at least MIN_CHANGE_PTS percentage points AND
   at least MIN_CHANGE_REL in relative terms.

2. A VOLUME floor. Skills that barely appear cannot support a claim
   about direction, so they are reported as 'insufficient data'.

3. VOLATILITY is recorded alongside the change. A skill that swings
   wildly month to month has a less trustworthy trend than a steady
   one, even when the headline change is identical.
"""

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
IN_FILE = ROOT / "data" / "processed" / "monthly_demand.parquet"
OUT_MONTHLY = ROOT / "data" / "processed" / "monthly_trends.parquet"
OUT_SUMMARY = ROOT / "data" / "processed" / "skill_trends.parquet"

WINDOW = 3                 # months in the recent / previous comparison windows
ROLLING = 3                # months in the smoothing window
MIN_CHANGE_PTS = 0.5       # absolute floor, in percentage points
MIN_CHANGE_REL = 10.0      # relative floor, in percent
MIN_TOTAL_MENTIONS = 100   # a skill below this cannot support a direction claim


def classify(row) -> str:
    if row["total_mentions"] < MIN_TOTAL_MENTIONS:
        return "insufficient data"
    if abs(row["change_pts"]) < MIN_CHANGE_PTS:
        return "stable"
    if abs(row["change_rel_pct"]) < MIN_CHANGE_REL:
        return "stable"
    return "rising" if row["change_pts"] > 0 else "declining"


def main() -> None:
    if not IN_FILE.exists():
        raise SystemExit(f"Missing {IN_FILE}. Run 04_aggregate.py first.")

    full = pd.read_parquet(IN_FILE).sort_values(["skill", "month"])

    # Everything below the headline charts uses ANALYSIS-GRADE months only.
    # 04_aggregate.py excluded months that were too small or whose
    # descriptions were truncated by the scraper. Including them made
    # every skill look like it was declining -- an artifact of shorter
    # text, not a change in demand.
    df = full[full["is_analysis_grade"]].copy()
    excluded = full["month"].nunique() - df["month"].nunique()

    # ---- Month-level: rolling average and month-over-month change -----
    grp = df.groupby("skill", group_keys=False)
    df["rolling_3m"] = grp["demand_pct"].transform(
        lambda s: s.rolling(ROLLING, min_periods=1).mean()
    )
    df["mom_change_pts"] = grp["demand_pct"].transform(lambda s: s.diff())

    # The month-level file keeps EVERY month, including excluded ones, so
    # the dashboard can draw them greyed out rather than silently hiding
    # a gap in the data. Only analysis-grade rows carry rolling/MoM values.
    monthly = full.merge(
        df[["month", "skill", "rolling_3m", "mom_change_pts"]],
        on=["month", "skill"], how="left",
    )
    monthly[["month", "skill", "category", "n_with_skill", "n_postings",
             "demand_pct", "rolling_3m", "mom_change_pts",
             "is_low_volume", "is_analysis_grade"]].to_parquet(
        OUT_MONTHLY, index=False
    )

    # ---- Skill-level summary -------------------------------------------
    months = sorted(df["month"].unique())
    recent_months = months[-WINDOW:]
    previous_months = months[-2 * WINDOW:-WINDOW]

    recent = df[df["month"].isin(recent_months)]
    previous = df[df["month"].isin(previous_months)]

    summary = (
        df.groupby(["skill", "category"], as_index=False)
        .agg(
            total_mentions=("n_with_skill", "sum"),
            overall_pct=("demand_pct", "mean"),
            volatility=("demand_pct", "std"),
            peak_pct=("demand_pct", "max"),
        )
    )

    # Weighted by postings, so a 272-posting month cannot swing the window
    # as hard as a 3,000-posting one.
    def weighted_pct(frame: pd.DataFrame) -> pd.Series:
        g = frame.groupby("skill")
        return g["n_with_skill"].sum() / g["n_postings"].sum() * 100

    summary = summary.merge(
        weighted_pct(recent).rename("recent_pct"), on="skill", how="left"
    ).merge(
        weighted_pct(previous).rename("previous_pct"), on="skill", how="left"
    ).merge(
        df[df["month"] == months[-1]].set_index("skill")["demand_pct"]
        .rename("latest_pct"),
        on="skill", how="left",
    )

    summary["change_pts"] = summary["recent_pct"] - summary["previous_pct"]
    summary["change_rel_pct"] = np.where(
        summary["previous_pct"] > 0,
        summary["change_pts"] / summary["previous_pct"] * 100,
        np.nan,
    )
    summary["direction"] = summary.apply(classify, axis=1)
    summary["volatility"] = summary["volatility"].fillna(0.0)

    summary = summary.sort_values("overall_pct", ascending=False).reset_index(drop=True)
    summary.to_parquet(OUT_SUMMARY, index=False)

    # ---- Report ---------------------------------------------------------
    r0, r1 = recent_months[0], recent_months[-1]
    p0, p1 = previous_months[0], previous_months[-1]
    print("=" * 72)
    print("TREND ANALYSIS REPORT")
    print("=" * 72)
    print(f"\nAnalysis-grade months used: {df['month'].nunique()}  "
          f"({months[0]:%b %Y} - {months[-1]:%b %Y})")
    print(f"Months excluded by the quality gate: {excluded}")
    print(f"\nComparing  {r0:%b %Y} - {r1:%b %Y}   against   {p0:%b %Y} - {p1:%b %Y}")
    print(f"Postings in recent window:   {recent['n_postings'].groupby(recent['month']).first().sum():,}")
    print(f"Postings in previous window: {previous['n_postings'].groupby(previous['month']).first().sum():,}")

    counts = summary["direction"].value_counts()
    print("\nSkills by direction:")
    for d in ["rising", "declining", "stable", "insufficient data"]:
        print(f"  {d:<20} {counts.get(d, 0):>3}")

    def table(title: str, frame: pd.DataFrame) -> None:
        print("\n" + "-" * 72)
        print(title)
        print("-" * 72)
        print(f"{'skill':<22} {'prev':>7} {'recent':>7} {'change':>8} "
              f"{'rel':>8}  {'vol':>5}")
        for _, r in frame.iterrows():
            print(f"{r['skill']:<22} {r['previous_pct']:>6.2f}% "
                  f"{r['recent_pct']:>6.2f}% {r['change_pts']:>+7.2f}p "
                  f"{r['change_rel_pct']:>+7.1f}% {r['volatility']:>5.2f}")

    rising = summary[summary["direction"] == "rising"].nlargest(12, "change_pts")
    declining = summary[summary["direction"] == "declining"].nsmallest(12, "change_pts")

    table("TOP RISING SKILLS", rising)
    table("TOP DECLINING SKILLS", declining)

    print("\n" + "-" * 72)
    print("GENERATIVE AI CATEGORY -- the headline finding")
    print("-" * 72)
    genai = full[full["category"] == "Generative AI"].groupby("month").agg(
        mentions=("n_with_skill", "sum"), postings=("n_postings", "first")
    )
    genai["pct_of_postings"] = genai["mentions"] / genai["postings"] * 100
    grade = full.groupby("month")["is_analysis_grade"].first()
    for month, r in genai.iterrows():
        bar = "#" * int(r["pct_of_postings"] * 8)
        flag = "" if grade[month] else "   <- excluded"
        print(f"  {month:%Y-%m}  {r['pct_of_postings']:5.2f}%  {bar}{flag}")

    print(f"\nWrote {OUT_MONTHLY.relative_to(ROOT)}")
    print(f"Wrote {OUT_SUMMARY.relative_to(ROOT)}\n")


if __name__ == "__main__":
    main()
