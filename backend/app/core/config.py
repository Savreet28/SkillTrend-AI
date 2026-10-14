"""Paths and constants. Everything that knows where files live lives here.

No module outside this file should hardcode a path. That way moving the
data directory is a one-line change rather than a hunt through the code.
"""

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
FORECASTS = FORECASTS_DIR / "forecasts.parquet"
MODEL_METRICS = FORECASTS_DIR / "model_metrics.json"

# Origins allowed to call this API from a browser.
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

API_TITLE = "SkillTrend AI API"
API_VERSION = "1.0.0"
API_DESCRIPTION = (
    "Skill demand analysis and forecasting over 58,276 data-analyst job "
    "postings (Nov 2022 - Apr 2025). Trends and forecasts use only "
    "analysis-grade months; see /api/summary for the data-quality report."
)
