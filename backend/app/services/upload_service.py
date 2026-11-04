"""Accept a user's own job-posting CSV and analyse it.

TWO MODES
  standalone  Analyse the upload alone. Forecasting requires >= 12 months
              of history IN THE UPLOAD; below that it is refused, with the
              reason, rather than faked.
  append      Splice the upload onto the end of the historical corpus so
              the forecast origin moves to the user's latest month. This
              is the "predict from today" case.

THE HONEST PROBLEM WITH APPEND
The two datasets are different populations. Splicing them is useful -- it
is the only way to move the forecast origin forward -- but it is not the
same as having one continuous corpus. So the join month is recorded and
returned, every response says which months came from where, and the UI
draws the seam.

LIMITS exist because this is designed to run on a free hosting tier:
50 MB and 200k rows, enforced before anything is parsed.
"""

from __future__ import annotations

import io
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.core import config
from app.services.data_store import get_store
from app.services.extraction import get_extractor

MAX_BYTES = 50 * 1024 * 1024
MAX_ROWS = 200_000
MIN_DESCRIPTION_CHARS = 100
MIN_MONTHS_TO_FORECAST = 12

# Column names we will accept without the user telling us which is which.
DATE_HINTS = ("date", "posted", "created", "listed", "time", "published")
TEXT_HINTS = ("description", "job_description", "text", "summary",
              "details", "requirements", "jobdescription")

URL_RE = re.compile(r"https?://\S+|www\.\S+")
WHITESPACE_RE = re.compile(r"\s+")


class UploadError(ValueError):
    """Bad input from the user. Always carries an actionable message."""


def _guess_column(columns: list[str], hints: tuple[str, ...]) -> str | None:
    lowered = {c: c.lower().replace(" ", "_") for c in columns}
    for col, low in lowered.items():
        if any(h == low for h in hints):
            return col
    for col, low in lowered.items():
        if any(h in low for h in hints):
            return col
    return None


def _clean_text(text: str) -> str:
    """Same normalisation as 02_clean.py. Punctuation is kept on purpose --
    stripping it would destroy C++, CI/CD and .NET."""
    text = URL_RE.sub(" ", str(text).lower())
    return WHITESPACE_RE.sub(" ", text).strip()


def _monthly_demand(df: pd.DataFrame, extractor) -> tuple[pd.DataFrame, dict]:
    """Extract skills and aggregate to skill x month, as % of postings."""
    texts = df["description"].map(_clean_text)

    rows: list[tuple[str, pd.Timestamp]] = []
    months = df["month"].tolist()
    hits = 0
    for i, skills in enumerate(extractor.extract_many(texts, batch_size=200)):
        if skills:
            hits += 1
        for skill in skills:
            rows.append((skill, months[i]))

    if not rows:
        raise UploadError(
            "No known skills were found in any posting. Check that the text "
            "column really contains job descriptions."
        )

    found = pd.DataFrame(rows, columns=["skill", "month"])
    totals = df.groupby("month").size().rename("n_postings")

    demand = (
        found.groupby(["skill", "month"]).size().rename("n_with_skill").reset_index()
        .merge(totals, on="month")
    )
    demand["demand_pct"] = demand["n_with_skill"] / demand["n_postings"] * 100
    demand["is_analysis_grade"] = True

    stats = {
        "hit_rate_pct": round(hits / len(df) * 100, 2),
        "skills_found": int(found["skill"].nunique()),
        "skill_mentions": int(len(found)),
    }
    return demand, stats


def process_upload(
    raw: bytes,
    filename: str,
    mode: str = "append",
    date_column: str | None = None,
    text_column: str | None = None,
) -> dict:
    """Validate, clean, extract and aggregate. Returns a summary dict."""
    if mode not in ("append", "standalone"):
        raise UploadError("mode must be 'append' or 'standalone'")
    if len(raw) > MAX_BYTES:
        raise UploadError(
            f"File is {len(raw) / 1e6:.1f} MB; the limit is {MAX_BYTES / 1e6:.0f} MB."
        )

    try:
        df = pd.read_csv(io.BytesIO(raw), low_memory=False)
    except Exception as exc:                            # noqa: BLE001
        raise UploadError(f"Could not read that as CSV: {exc}") from exc

    if df.empty:
        raise UploadError("The file has no rows.")
    if len(df) > MAX_ROWS:
        raise UploadError(f"{len(df):,} rows; the limit is {MAX_ROWS:,}.")

    columns = list(df.columns)
    date_col = date_column or _guess_column(columns, DATE_HINTS)
    text_col = text_column or _guess_column(columns, TEXT_HINTS)

    if date_col is None:
        raise UploadError(
            f"No date column found. Columns present: {', '.join(columns[:15])}. "
            f"Pass date_column explicitly."
        )
    if text_col is None:
        raise UploadError(
            f"No job-description column found. Columns present: "
            f"{', '.join(columns[:15])}. Pass text_column explicitly."
        )

    work = pd.DataFrame({
        "posted_at": pd.to_datetime(df[date_col], errors="coerce",
                                    format="mixed", utc=True),
        "description": df[text_col].astype(str),
    })
    work["posted_at"] = work["posted_at"].dt.tz_convert(None)

    rows_in = len(work)
    work = work.dropna(subset=["posted_at"])
    bad_dates = rows_in - len(work)
    work = work[work["description"].str.len() >= MIN_DESCRIPTION_CHARS]
    short_text = rows_in - bad_dates - len(work)

    if work.empty:
        raise UploadError(
            f"Nothing usable left: {bad_dates} rows had unparseable dates and "
            f"{short_text} had descriptions under {MIN_DESCRIPTION_CHARS} characters."
        )

    work["month"] = work["posted_at"].dt.to_period("M").dt.to_timestamp()

    store = get_store()
    demand, extract_stats = _monthly_demand(work, get_extractor())

    # ---- Assemble the series this upload will be analysed against -------
    own_months = sorted(demand["month"].unique())
    join_month = None
    combined = demand

    if mode == "append":
        base = store.monthly[store.monthly["is_analysis_grade"]][
            ["month", "skill", "n_with_skill", "n_postings", "demand_pct",
             "is_analysis_grade"]
        ].copy()
        base["source"] = "historical"
        mine = demand.copy()
        mine["source"] = "upload"

        # The upload wins where the two overlap: it is the fresher view.
        overlap = set(base["month"]) & set(mine["month"])
        if overlap:
            base = base[~base["month"].isin(overlap)]
        combined = pd.concat([base, mine], ignore_index=True)
        join_month = pd.Timestamp(min(own_months))
    else:
        combined = demand.copy()
        combined["source"] = "upload"

    n_months = combined["month"].nunique()
    can_forecast = n_months >= MIN_MONTHS_TO_FORECAST

    upload_id = uuid.uuid4().hex[:12]
    out_dir = config.UPLOAD_DIR / upload_id
    out_dir.mkdir(parents=True, exist_ok=True)
    combined.sort_values(["skill", "month"]).to_parquet(
        out_dir / "monthly.parquet", index=False
    )

    summary = {
        "upload_id": upload_id,
        "filename": filename,
        "mode": mode,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "columns_used": {"date": date_col, "description": text_col},
        "rows_in_file": rows_in,
        "rows_used": int(len(work)),
        "rows_dropped": {"bad_dates": int(bad_dates), "short_text": int(short_text)},
        "own_months": len(own_months),
        "own_range": [str(pd.Timestamp(own_months[0]).date()),
                      str(pd.Timestamp(own_months[-1]).date())],
        "total_months": int(n_months),
        "forecast_origin": str(combined["month"].max().date()),
        "join_month": str(join_month.date()) if join_month is not None else None,
        "can_forecast": bool(can_forecast),
        **extract_stats,
    }

    if not can_forecast:
        summary["forecast_refused_because"] = (
            f"Only {n_months} months of history. A 6-month forecast needs at "
            f"least {MIN_MONTHS_TO_FORECAST}. Skills were still extracted and "
            f"ranked — just no projection."
        )
    if mode == "append":
        summary["caveat"] = (
            "Your data is spliced onto the historical corpus, which is US "
            "data-analyst postings from 2022-24. They are different "
            "populations; the join month is marked so you can see the seam. "
            "Treat a jump at the join as a change of source, not of market."
        )

    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def load_upload(upload_id: str) -> tuple[pd.DataFrame, dict]:
    out_dir = config.UPLOAD_DIR / upload_id
    if not (out_dir / "summary.json").exists():
        raise UploadError(f"Unknown upload id: {upload_id}")
    monthly = pd.read_parquet(out_dir / "monthly.parquet")
    summary = json.loads((out_dir / "summary.json").read_text())
    return monthly, summary


def delete_upload(upload_id: str) -> None:
    out_dir = config.UPLOAD_DIR / upload_id
    if out_dir.exists():
        shutil.rmtree(out_dir)
