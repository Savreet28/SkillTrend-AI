"""Step 2 of the pipeline: clean the raw dataset.

Input:  data/raw/gsearch_jobs.csv        (61,953 rows, 27 columns)
Output: data/processed/clean_postings.parquet

Every decision here is driven by what 01_load.py actually found in
the data -- not by assumptions about what job postings usually look like.
"""

import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_FILE = ROOT / "data" / "raw" / "gsearch_jobs.csv"
OUT_FILE = ROOT / "data" / "processed" / "clean_postings.parquet"

# Only the columns we actually need. 17 of the 27 are dropped:
# salary_* (84-93% empty), commute_time (100% empty), thumbnail,
# extensions, posted_at ("15 hours ago" - useless), Unnamed: 0 and
# index (leftover row numbers), and search_term (always "data analyst").
KEEP_COLUMNS = [
    "job_id",
    "title",
    "company_name",
    "location",
    "via",
    "schedule_type",
    "date_time",
    "description",
    "description_tokens",
]

MIN_DESCRIPTION_CHARS = 100

URL_RE = re.compile(r"https?://\S+|www\.\S+")
EMAIL_RE = re.compile(r"\S+@\S+\.\S+")
WHITESPACE_RE = re.compile(r"\s+")


def clean_text(text: str) -> str:
    """Normalise a job description for skill matching.

    NOTE what this deliberately does NOT do: strip punctuation.
    Removing punctuation would turn "C++" into "c", ".NET" into "net",
    "Node.js" into "node js" and "CI/CD" into "ci cd" -- destroying the
    exact tokens we need to match in Phase 4. Punctuation is signal here,
    not noise.
    """
    text = text.lower()
    text = URL_RE.sub(" ", text)
    text = EMAIL_RE.sub(" ", text)
    text = WHITESPACE_RE.sub(" ", text)
    return text.strip()


def main() -> None:
    if not RAW_FILE.exists():
        raise SystemExit(f"File not found: {RAW_FILE}")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    report: list[tuple[str, int]] = []

    df = pd.read_csv(RAW_FILE, usecols=KEEP_COLUMNS, low_memory=False)
    report.append(("loaded", len(df)))

    # --- 1. Parse the date -------------------------------------------
    # date_time is when the scraper SAW the posting, not when the employer
    # published it. posted_at says things like "15 hours ago", so the two
    # are within a day or so. At monthly granularity that is fine -- but
    # it is a real caveat and belongs in the README.
    df["posted_at_dt"] = pd.to_datetime(
        df["date_time"], errors="coerce", format="mixed", utc=True
    ).dt.tz_convert(None)

    df = df.dropna(subset=["posted_at_dt"])
    report.append(("after dropping unparseable dates", len(df)))

    # --- 2. Drop unusable descriptions -------------------------------
    # The shortest description in the raw data is 1 character.
    df = df.dropna(subset=["description"])
    df = df[df["description"].str.len() >= MIN_DESCRIPTION_CHARS]
    report.append((f"after dropping descriptions < {MIN_DESCRIPTION_CHARS} chars", len(df)))

    # --- 3. Deduplicate ----------------------------------------------
    # Daily scraping caught ~5% of listings more than once. Keeping the
    # EARLIEST sighting puts each job in the month it first appeared,
    # which is closest to when it was actually posted.
    df = df.sort_values("posted_at_dt").drop_duplicates("job_id", keep="first")
    report.append(("after deduplicating on job_id", len(df)))

    # --- 4. Add the month bucket -------------------------------------
    # Stored as the first day of the month (a real timestamp) rather than
    # a pandas Period, because Parquet cannot store Period objects.
    df["month"] = df["posted_at_dt"].dt.to_period("M").dt.to_timestamp()

    # --- 5. Clean the text -------------------------------------------
    print("Cleaning description text...")
    df["description_clean"] = df["description"].map(clean_text)

    # --- 6. Save ------------------------------------------------------
    final = df[
        [
            "job_id",
            "title",
            "company_name",
            "location",
            "via",
            "schedule_type",
            "posted_at_dt",
            "month",
            "description_clean",
            "description_tokens",
        ]
    ].reset_index(drop=True)

    final.to_parquet(OUT_FILE, index=False)

    # --- Report -------------------------------------------------------
    print("\n" + "=" * 62)
    print("CLEANING REPORT")
    print("=" * 62 + "\n")

    start = report[0][1]
    previous = start
    for label, count in report:
        delta = count - previous
        change = f"  ({delta:+,})" if delta else ""
        print(f"{label:<46} {count:>8,}{change}")
        previous = count

    removed = start - len(final)
    print(f"\nRemoved {removed:,} rows total ({removed / start * 100:.1f}%)")

    print(f"\nDate range:      {final['posted_at_dt'].min().date()} -> "
          f"{final['posted_at_dt'].max().date()}")
    print(f"Distinct months: {final['month'].nunique()}")
    print(f"Output:          {OUT_FILE.relative_to(ROOT)} "
          f"({OUT_FILE.stat().st_size / 1_000_000:.0f} MB)")

    print("\nSample cleaned text (first 300 chars):\n")
    print(final["description_clean"].iloc[0][:300] + "...")
    print()


if __name__ == "__main__":
    main()