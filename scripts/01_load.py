"""Step 1 of the pipeline: load the raw dataset and inspect it.

This script CHANGES NOTHING. It only reads and reports.

Why a dedicated inspection step? You cannot write correct cleaning
code against a dataset whose columns, types and gaps you have only
guessed at. Everything downstream depends on facts established here.

It also measures the first Data Gate number: how many distinct months
the data actually covers. That decides whether forecasting is honest.
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_FILE = ROOT / "data" / "raw" / "gsearch_jobs.csv"

CHUNK_SIZE = 50_000
DATE_HINTS = ("date", "time", "posted", "created", "listed")


def find_date_candidates(columns) -> list[str]:
    """Columns whose NAME suggests they hold a date."""
    return [c for c in columns if any(h in c.lower() for h in DATE_HINTS)]


def main() -> None:
    if not RAW_FILE.exists():
        raise SystemExit(f"File not found: {RAW_FILE}\nDid Step 4 finish?")

    print(f"\nFile: {RAW_FILE.name}  ({RAW_FILE.stat().st_size / 1_000_000:.0f} MB)")

    # ---- Stage 1: peek at a small slice --------------------------------
    print("\n" + "=" * 70)
    print("STAGE 1 — COLUMNS (from first 1,000 rows)")
    print("=" * 70)

    sample = pd.read_csv(RAW_FILE, nrows=1_000, low_memory=False)

    print(f"\n{len(sample.columns)} columns:\n")
    for i, col in enumerate(sample.columns, start=1):
        non_null = sample[col].dropna()
        example = str(non_null.iloc[0]).replace("\n", " ")[:55] if len(non_null) else "—"
        print(f"{i:>3}. {col:<28} {str(sample[col].dtype):<9} e.g. {example}")

    date_candidates = find_date_candidates(sample.columns)
    print(f"\nPossible date columns: {date_candidates or 'NONE FOUND'}")

    # ---- Stage 2: scan the whole file in chunks ------------------------
    print("\n" + "=" * 70)
    print("STAGE 2 — FULL SCAN (reading in chunks)")
    print("=" * 70)
    print("\nScanning... (a minute or so)\n")

    total_rows = 0
    null_counts = None
    parsed_dates: dict[str, list] = {c: [] for c in date_candidates}

    for chunk in pd.read_csv(RAW_FILE, chunksize=CHUNK_SIZE, low_memory=False):
        total_rows += len(chunk)

        counts = chunk.isna().sum()
        null_counts = counts if null_counts is None else null_counts + counts

        for col in date_candidates:
            parsed = pd.to_datetime(chunk[col], errors="coerce", format="mixed", utc=True)
            parsed_dates[col].append(parsed.dropna())

        print(f"  ...{total_rows:,} rows", end="\r")

    print(f"\nTotal rows: {total_rows:,}")

    # ---- Stage 3: missing values ---------------------------------------
    print("\n" + "=" * 70)
    print("STAGE 3 — MISSING VALUES (columns with gaps)")
    print("=" * 70 + "\n")

    gaps = null_counts[null_counts > 0].sort_values(ascending=False)
    if gaps.empty:
        print("No missing values anywhere.")
    else:
        for col, count in gaps.items():
            print(f"{col:<28} {count:>10,}  ({count / total_rows * 100:5.1f}%)")

    # ---- Stage 4: THE DATA GATE ----------------------------------------
    print("\n" + "=" * 70)
    print("STAGE 4 — DATA GATE: how much history do we actually have?")
    print("=" * 70)

    for col, pieces in parsed_dates.items():
        series = pd.concat(pieces) if pieces else pd.Series(dtype="datetime64[ns, UTC]")

        print(f"\n--- {col} ---")
        if series.empty:
            print("  Nothing parsed as a date. Not usable.")
            continue

        months = series.dt.to_period("M")
        per_month = months.value_counts().sort_index()

        print(f"  Parsed OK:      {len(series):,} of {total_rows:,} rows")
        print(f"  Range:          {series.min().date()}  ->  {series.max().date()}")
        print(f"  Distinct months: {months.nunique()}")
        print(f"  Median postings/month: {int(per_month.median()):,}")
        print("\n  Postings per month:")
        for period, count in per_month.items():
            bar = "#" * min(int(count / max(per_month.max(), 1) * 40), 40)
            print(f"    {period}  {count:>7,}  {bar}")

    print("\nDone. Nothing was modified.\n")


if __name__ == "__main__":
    main()