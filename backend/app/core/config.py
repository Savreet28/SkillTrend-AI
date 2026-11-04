"""Paths and constants. Everything that knows where files live lives here.

No module outside this file should hardcode a path. That way moving the
data directory is a one-line change rather than a hunt through the code.
"""

import os
from pathlib import Path

# backend/app/core/config.py -> up four levels is the project root
ROOT = Path(__file__).resolve().parents[3]

DATA_DIR = ROOT / "data"
PROCESSED_DIR = DATA_DIR / "processed"
FORECASTS_DIR = DATA_DIR / "forecasts"
SKILLS_DIR = ROOT / "skills"

MONTHLY_TRENDS = PROCESSED_DIR / "monthly_trends.parquet"
MONTHLY_TOTALS = PROCESSED_DIR / "monthly_totals.parquet"
SKILL_TRENDS = PROCESSED_DIR / "skill_trends.parquet"
CATEGORY_MONTHLY = PROCESSED_DIR / "category_monthly.parquet"
EXTRACTION_STATS = PROCESSED_DIR / "extraction_stats.json"

# Role comparison + live feed (scripts 07 and 08). Optional: the API still
# starts without them, it just reports roles as unavailable.
LIVE_DIR = DATA_DIR / "live"
LIVE_POSTINGS = LIVE_DIR / "live_postings.parquet"
ROLE_PROFILES = PROCESSED_DIR / "role_profiles.parquet"
ROLE_MONTHLY = PROCESSED_DIR / "role_monthly.parquet"
ROLE_STATS = PROCESSED_DIR / "role_stats.json"

# Decide engine (scripts 09 and 10)
SKILL_GRAPH = PROCESSED_DIR / "skill_graph.parquet"
SKILL_RELATIONS = PROCESSED_DIR / "skill_relations.parquet"
SKILL_FAMILIES = PROCESSED_DIR / "skill_families.json"

# User uploads. Gitignored: these are the user's own data, per install.
UPLOAD_DIR = DATA_DIR / "uploads"
FORECASTS = FORECASTS_DIR / "forecasts.parquet"
MODEL_METRICS = FORECASTS_DIR / "model_metrics.json"

# Origins allowed to call this API from a browser.
#
# Local dev origins are always allowed. On a deployed instance set
# SKILLTREND_CORS_ORIGINS to a comma-separated list of frontend URLs, so
# deploying never requires editing code.
_DEFAULT_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
CORS_ORIGINS = _DEFAULT_ORIGINS + [
    origin.strip()
    for origin in os.environ.get("SKILLTREND_CORS_ORIGINS", "").split(",")
    if origin.strip()
]

API_TITLE = "SkillTrend AI API"
API_VERSION = "1.0.0"
API_DESCRIPTION = (
    "Skill demand analysis and forecasting over 58,276 data-analyst job "
    "postings (Nov 2022 - Apr 2025). Trends and forecasts use only "
    "analysis-grade months; see /api/summary for the data-quality report."
)
