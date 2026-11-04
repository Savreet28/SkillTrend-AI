"""Step 7: fetch fresh job postings from free, official job-board APIs.

Output: data/live/live_postings.parquet   (appended to, never overwritten)

WHY APIs AND NOT A SCRAPER
The original idea was to scrape Google job results with Selenium or
BeautifulSoup. That was rejected for three reasons:
  * Google serves CAPTCHAs to automated traffic, and defeating those is
    both against their terms and not something this project will do.
  * Apify (the other option considered) is a paid service.
  * A Selenium scraper on a monthly cron breaks within weeks.
These three APIs are published by the job boards themselves, are free,
need no key at all, and return the full job description. Same outcome,
legitimately.

HOW APPENDING WORKS
Each run fetches whatever is currently listed and merges it into the
existing Parquet, deduplicating on a stable id. Job boards only show
current openings, so running this monthly builds up a history that no
single download could give you. The file therefore GROWS over time and
is the one data file that IS committed to Git -- otherwise every
scheduled run would start from nothing.

Run:  python scripts/07_fetch_live.py [--pages N]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from roles import classify_role  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "live"
OUT_FILE = OUT_DIR / "live_postings.parquet"

USER_AGENT = "SkillTrendAI/1.0 (student project; +https://github.com)"
TIMEOUT = 40
POLITE_DELAY = 1.0          # seconds between requests - do not hammer free APIs
MIN_DESCRIPTION_CHARS = 100

# This file is COMMITTED and appended to every month, so it must not grow
# without bound. Descriptions are ~2.5 KB each and are only needed once --
# 08_roles.py extracts skills from them and stores the result separately
# in live_skills.parquet. After this many months we blank the description
# and keep only the metadata, which keeps the file flat instead of adding
# ~8 MB a month until GitHub refuses it.
DESCRIPTION_RETENTION_MONTHS = 3

# Arbeitnow is a general job board covering all industries, so roughly
# four in five postings are not tech at all. Its documented `search`
# parameter turns out to be IGNORED -- search=engineer and search=nurse
# return byte-identical results -- so there is no way to filter server
# side. We page through everything and classify afterwards instead.
# Pagination runs out around page 25.
ARBEITNOW_MAX_PAGES = 25

# Only these Jobicy industry slugs are valid AND tech-relevant; the API
# returns HTTP 400 for anything it does not recognise.
JOBICY_INDUSTRIES = ["engineering", "data-science"]

# Guard against nonsense dates (an unparsed Unix 0 shows up as 1970).
EARLIEST_SANE_DATE = pd.Timestamp("2015-01-01")

TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


def http_json(url: str) -> dict | None:
    """GET a URL and parse JSON. Returns None on any failure.

    A dead API must never kill the whole run -- the other sources should
    still contribute, and the scheduled job should still succeed.
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        print(f"    ! {type(exc).__name__}: {exc}")
        return None


def unix_to_iso(value) -> str | None:
    """Arbeitnow gives integer epoch seconds; everything else gives ISO text."""
    if value in (None, "", 0):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return str(value)


def clean_html(text: str | None) -> str:
    """These APIs return HTML descriptions -- unlike the Kaggle corpus."""
    if not text:
        return ""
    text = TAG_RE.sub(" ", text)
    for entity, char in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                         ("&nbsp;", " "), ("&quot;", '"'), ("&#39;", "'")):
        text = text.replace(entity, char)
    return WHITESPACE_RE.sub(" ", text).strip()


def make_id(source: str, native_id: str, title: str, company: str) -> str:
    """Stable id. Falls back to a content hash when the API gives no id."""
    seed = native_id or f"{title}|{company}"
    return f"{source}:{hashlib.sha1(seed.encode()).hexdigest()[:16]}"


# --------------------------------------------------------------------------
# One function per source. Each returns a list of dicts in OUR schema.
# --------------------------------------------------------------------------

def fetch_arbeitnow(pages: int) -> list[dict]:
    """300 jobs per page, paged until the board runs out."""
    out: list[dict] = []
    base = "https://www.arbeitnow.com/api/job-board-api"
    pages = min(pages, ARBEITNOW_MAX_PAGES)

    for page in range(1, pages + 1):
            data = http_json(f"{base}?{urllib.parse.urlencode({'page': page})}")
            if not data or not data.get("data"):
                print(f"    stopped at page {page} (no more results)")
                break

            for job in data["data"]:
                out.append({
                    "job_id": make_id("arbeitnow", job.get("slug", ""),
                                      job.get("title", ""), job.get("company_name", "")),
                    "source": "arbeitnow",
                    "title": job.get("title", ""),
                    "company": job.get("company_name", ""),
                    "location": job.get("location", ""),
                    "description": clean_html(job.get("description")),
                    # created_at is a UNIX TIMESTAMP (integer seconds), not a
                    # date string. Parsing it as text yields 1970-01-01.
                    "posted_at": unix_to_iso(job.get("created_at")),
                    "url": job.get("url", ""),
                })
            if page % 5 == 0:
                print(f"    page {page:>2}: {len(out):>5} jobs so far")

            if not data.get("links", {}).get("next"):
                break
            time.sleep(POLITE_DELAY)

    print(f"    {len(out):>5} jobs total")
    return out


def fetch_jobicy() -> list[dict]:
    """Capped at 100 per call, so we call once per tech industry.

    Jobicy has its own industry labels, but we still classify from the
    title ourselves -- every source must be labelled the same way or the
    role comparison is meaningless.
    """
    out: list[dict] = []
    for industry in JOBICY_INDUSTRIES:
        data = http_json(
            f"https://jobicy.com/api/v2/remote-jobs?count=100&industry={industry}"
        )
        jobs = (data or {}).get("jobs", [])
        print(f"    {industry:<20} {len(jobs):>5} jobs")
        out.extend(_jobicy_rows(jobs))
        time.sleep(POLITE_DELAY)
    return out


def _jobicy_rows(jobs: list[dict]) -> list[dict]:
    out = []
    for job in jobs:
        out.append({
            "job_id": make_id("jobicy", str(job.get("id", "")),
                              job.get("jobTitle", ""), job.get("companyName", "")),
            "source": "jobicy",
            "title": job.get("jobTitle", ""),
            "company": job.get("companyName", ""),
            "location": job.get("jobGeo", ""),
            "description": clean_html(job.get("jobDescription")),
            "posted_at": job.get("pubDate"),
            "url": job.get("url", ""),
        })
    return out


def fetch_remotive() -> list[dict]:
    """Small without an API key, but free and adds variety."""
    data = http_json("https://remotive.com/api/remote-jobs")
    if not data:
        return []

    out = []
    for job in data.get("jobs", []):
        out.append({
            "job_id": make_id("remotive", str(job.get("id", "")),
                              job.get("title", ""), job.get("company_name", "")),
            "source": "remotive",
            "title": job.get("title", ""),
            "company": job.get("company_name", ""),
            "location": job.get("candidate_required_location", ""),
            "description": clean_html(job.get("description")),
            "posted_at": job.get("publication_date"),
            "url": job.get("url", ""),
        })
    print(f"    {len(out)} jobs")
    return out


# --------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=int, default=25,
                        help="Arbeitnow pages to fetch (300 jobs each, max 25)")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fetched_at = datetime.now(timezone.utc)

    print("=" * 68)
    print(f"FETCHING LIVE JOB POSTINGS  —  {fetched_at:%Y-%m-%d %H:%M UTC}")
    print("=" * 68)

    rows: list[dict] = []
    for name, fn in (("arbeitnow", lambda: fetch_arbeitnow(args.pages)),
                     ("jobicy", fetch_jobicy),
                     ("remotive", fetch_remotive)):
        print(f"\n  {name}")
        try:
            rows.extend(fn())
        except Exception as exc:                        # noqa: BLE001
            print(f"    ! {name} failed entirely: {exc}")

    if not rows:
        raise SystemExit("\nNo postings fetched from any source. Nothing written.")

    fresh = pd.DataFrame(rows)
    fetched_raw = len(fresh)

    # ---- Clean ---------------------------------------------------------
    fresh["posted_at"] = pd.to_datetime(
        fresh["posted_at"], errors="coerce", format="mixed", utc=True
    ).dt.tz_convert(None)
    # Some boards omit a date; the fetch time is the best honest proxy.
    fresh["posted_at"] = fresh["posted_at"].fillna(fetched_at.replace(tzinfo=None))

    # A date before 2015 means a parse failure, not a genuinely old posting.
    bad_dates = (fresh["posted_at"] < EARLIEST_SANE_DATE).sum()
    if bad_dates:
        print(f"\n  ! {bad_dates} rows had unparseable dates; using fetch time instead")
        fresh.loc[fresh["posted_at"] < EARLIEST_SANE_DATE, "posted_at"] = \
            fetched_at.replace(tzinfo=None)

    fresh = fresh[fresh["description"].str.len() >= MIN_DESCRIPTION_CHARS]
    fresh = fresh.drop_duplicates("job_id", keep="first")

    fresh["role"] = fresh["title"].map(classify_role)
    fresh["month"] = fresh["posted_at"].dt.to_period("M").dt.to_timestamp()
    fresh["first_seen"] = fetched_at.replace(tzinfo=None)

    # ---- Merge with what we already have --------------------------------
    if OUT_FILE.exists():
        existing = pd.read_parquet(OUT_FILE)
        before = len(existing)
        combined = pd.concat([existing, fresh], ignore_index=True)
        # keep="first" preserves the ORIGINAL first_seen date for a job we
        # have seen before, so re-listings don't reset its age.
        combined = combined.drop_duplicates("job_id", keep="first")
        added = len(combined) - before
    else:
        before, combined, added = 0, fresh, len(fresh)

    combined = combined.sort_values("posted_at").reset_index(drop=True)

    # ---- Prune old description text ------------------------------------
    cutoff = pd.Timestamp.now().normalize() - pd.DateOffset(
        months=DESCRIPTION_RETENTION_MONTHS
    )
    stale = (combined["posted_at"] < cutoff) & (combined["description"].str.len() > 0)
    pruned = int(stale.sum())
    if pruned:
        combined.loc[stale, "description"] = ""

    combined.to_parquet(OUT_FILE, index=False)

    # ---- Report ----------------------------------------------------------
    print("\n" + "=" * 68)
    print("FETCH REPORT")
    print("=" * 68)
    print(f"\nFetched from APIs      {fetched_raw:,}")
    print(f"Usable after cleaning  {len(fresh):,}")
    print(f"Already had            {before:,}")
    print(f"NEW this run           {added:,}")
    print(f"Total stored           {len(combined):,}")
    if pruned:
        print(f"Descriptions pruned    {pruned:,} "
              f"(older than {DESCRIPTION_RETENTION_MONTHS} months)")

    print("\nBy source:")
    for src, n in combined["source"].value_counts().items():
        print(f"  {src:<14} {n:>7,}")

    print("\nBy role:")
    total = len(combined)
    for role, n in combined["role"].value_counts().items():
        bar = "#" * int(n / total * 50)
        print(f"  {role:<28} {n:>6,}  {n / total * 100:5.1f}%  {bar}")

    other = combined[combined["role"] == "Other"]
    if len(other):
        print(f"\n  Unclassified sample (to improve scripts/roles.py):")
        for t in other["title"].drop_duplicates().head(8):
            print(f"    - {t[:66]}")

    print(f"\nDate range  {combined['posted_at'].min():%Y-%m-%d} -> "
          f"{combined['posted_at'].max():%Y-%m-%d}")
    print(f"Months      {combined['month'].nunique()}")
    print(f"\nWrote {OUT_FILE.relative_to(ROOT)} "
          f"({OUT_FILE.stat().st_size / 1_000_000:.1f} MB)\n")


if __name__ == "__main__":
    main()
