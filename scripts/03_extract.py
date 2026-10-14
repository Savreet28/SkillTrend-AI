"""Step 3 of the pipeline: extract skills from every job posting.

Input:  data/processed/clean_postings.parquet
Output: data/processed/posting_skills.parquet   (long format: one row per posting x skill)
        data/processed/extraction_stats.json    (quality metrics)

The output is deliberately LONG rather than a list column: one row per
(job_id, skill). Long format is what every downstream groupby wants, and
Parquet stores it efficiently.

This script also validates itself against the dataset's own
`description_tokens` column -- a skill list produced by whoever built the
Kaggle dataset. That list is NOT ground truth (it was frozen in 2022 and
contains no GenAI terms at all), but agreement/disagreement with it is a
useful sanity check and an honest point of comparison.
"""

from __future__ import annotations

import ast
import json
import time
from collections import Counter
from pathlib import Path

import pandas as pd

from skill_extractor import SkillExtractor

ROOT = Path(__file__).resolve().parent.parent
IN_FILE = ROOT / "data" / "processed" / "clean_postings.parquet"
OUT_FILE = ROOT / "data" / "processed" / "posting_skills.parquet"
STATS_FILE = ROOT / "data" / "processed" / "extraction_stats.json"


def main() -> None:
    if not IN_FILE.exists():
        raise SystemExit(f"Missing {IN_FILE}. Run 02_clean.py first.")

    extractor = SkillExtractor()
    print(f"Loaded {extractor.skill_count} skills across "
          f"{len(extractor.categories)} categories")

    df = pd.read_parquet(
        IN_FILE, columns=["job_id", "month", "description_clean", "description_tokens"]
    )
    print(f"Loaded {len(df):,} postings\n")

    # ---- Extract ------------------------------------------------------
    print("Extracting skills (this takes a few minutes)...")
    started = time.time()

    rows: list[tuple[str, pd.Timestamp, str]] = []
    per_posting_counts: list[int] = []

    job_ids = df["job_id"].tolist()
    months = df["month"].tolist()

    for i, skills in enumerate(extractor.extract_many(df["description_clean"], batch_size=500)):
        per_posting_counts.append(len(skills))
        job_id, month = job_ids[i], months[i]
        for skill in skills:
            rows.append((job_id, month, skill))

        if (i + 1) % 5_000 == 0:
            rate = (i + 1) / (time.time() - started)
            print(f"  {i + 1:>7,} / {len(df):,}   ({rate:.0f} postings/sec)")

    elapsed = time.time() - started
    print(f"  done in {elapsed / 60:.1f} min\n")

    skills_df = pd.DataFrame(rows, columns=["job_id", "month", "skill"])
    skills_df["category"] = skills_df["skill"].map(extractor.category_of)
    skills_df.to_parquet(OUT_FILE, index=False)

    # ---- Quality report ----------------------------------------------
    counts = pd.Series(per_posting_counts)
    hit_rate = (counts > 0).mean() * 100

    print("=" * 66)
    print("EXTRACTION REPORT")
    print("=" * 66)
    print(f"\nPostings processed      {len(df):,}")
    print(f"Skill mentions found    {len(skills_df):,}")
    print(f"Distinct skills seen    {skills_df['skill'].nunique()} "
          f"of {extractor.skill_count}")
    print(f"\nHIT RATE                {hit_rate:.1f}%  "
          f"(postings with >= 1 skill)   [gate: >= 70%]")
    print(f"Skills per posting      mean {counts.mean():.1f}  "
          f"median {int(counts.median())}  max {counts.max()}")

    # Skills in the dictionary that never matched -- dead weight worth knowing about
    never_seen = sorted(set(extractor.category_of) - set(skills_df["skill"]))
    if never_seen:
        print(f"\nNever matched ({len(never_seen)}): {', '.join(never_seen)}")

    # ---- Top skills ----------------------------------------------------
    n_postings = len(df)
    top = (
        skills_df.groupby("skill")["job_id"].nunique()
        .sort_values(ascending=False)
    )
    print("\n" + "-" * 66)
    print("TOP 25 SKILLS")
    print("-" * 66)
    for rank, (skill, n) in enumerate(top.head(25).items(), start=1):
        cat = extractor.category_of[skill]
        print(f"{rank:>3}. {skill:<22} {n:>7,}  {n / n_postings * 100:5.2f}%   {cat}")

    # ---- Category coverage ---------------------------------------------
    print("\n" + "-" * 66)
    print("POSTINGS MENTIONING EACH CATEGORY")
    print("-" * 66)
    cat_cov = (
        skills_df.groupby("category")["job_id"].nunique()
        .sort_values(ascending=False)
    )
    for cat, n in cat_cov.items():
        print(f"  {cat:<32} {n:>7,}  {n / n_postings * 100:5.2f}%")

    # ---- Cross-check against the dataset's own labels -------------------
    print("\n" + "-" * 66)
    print("CROSS-CHECK vs the dataset's own `description_tokens`")
    print("-" * 66)

    their_hits = 0
    their_tokens: Counter[str] = Counter()
    for raw in df["description_tokens"].fillna("[]"):
        try:
            toks = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            toks = []
        if toks:
            their_hits += 1
            their_tokens.update(toks)

    their_rate = their_hits / n_postings * 100
    print(f"  Their hit rate   {their_rate:5.1f}%")
    print(f"  Our hit rate     {hit_rate:5.1f}%   "
          f"({hit_rate - their_rate:+.1f} pts)")
    print(f"  Their vocabulary {len(their_tokens)} terms   "
          f"vs our {extractor.skill_count}")

    genai = sorted(
        s for s in skills_df["skill"].unique()
        if extractor.category_of[s] == "Generative AI"
    )
    print(f"\n  GenAI skills we detect that their vocabulary lacks entirely:")
    print(f"    {', '.join(genai)}")

    # ---- Persist stats --------------------------------------------------
    stats = {
        "postings": int(n_postings),
        "skill_mentions": int(len(skills_df)),
        "distinct_skills_found": int(skills_df["skill"].nunique()),
        "dictionary_size": int(extractor.skill_count),
        "hit_rate_pct": round(float(hit_rate), 2),
        "baseline_hit_rate_pct": round(float(their_rate), 2),
        "mean_skills_per_posting": round(float(counts.mean()), 2),
        "never_matched": never_seen,
        "extraction_seconds": round(elapsed, 1),
    }
    STATS_FILE.write_text(json.dumps(stats, indent=2))

    print(f"\nWrote {OUT_FILE.relative_to(ROOT)} "
          f"({OUT_FILE.stat().st_size / 1_000_000:.1f} MB)")
    print(f"Wrote {STATS_FILE.relative_to(ROOT)}\n")


if __name__ == "__main__":
    main()
