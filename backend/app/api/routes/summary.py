"""Dashboard summary: everything the overview page needs, in one request."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes.skills import row_to_summary
from app.schemas.models import DataQuality, ModelQuality, Summary
from app.services.data_store import get_store

router = APIRouter(tags=["summary"])


@router.get("/summary", response_model=Summary)
def get_summary() -> Summary:
    """One call powers the whole dashboard landing page.

    Includes the data-quality and model-quality reports, so the UI
    cannot show headline numbers without the context that qualifies them.
    """
    store = get_store()

    totals = store.totals
    analysis = store.analysis_months
    a_start, a_end = store.analysis_range()
    d_start, d_end = store.date_range()

    excluded = int(len(totals) - len(analysis))
    quality = DataQuality(
        total_months=int(len(totals)),
        analysis_grade_months=int(len(analysis)),
        excluded_months=excluded,
        analysis_start=a_start,
        analysis_end=a_end,
        exclusion_reason=(
            f"{excluded} months were excluded from all trends and forecasts: "
            f"some had too few postings (<1,000) and some had truncated job "
            f"descriptions (median <2,000 characters vs ~3,000 normally). "
            f"Including them made every skill appear to decline -- an artifact "
            f"of shorter text, not a change in demand."
        ),
    )

    m = store.metrics
    model = None
    if m:
        better = m["prophet_better_overall"]
        model = ModelQuality(
            skills_modelled=m["skills_modelled"],
            skills_beating_baseline=m["skills_beating_baseline"],
            pct_beating_baseline=m["pct_beating_baseline"],
            mean_prophet_mae=m["mean_prophet_mae"],
            mean_naive_mae=m["mean_naive_mae"],
            prophet_better_overall=better,
            verdict=(
                f"Prophet beat a naive carry-forward baseline on "
                f"{m['skills_beating_baseline']} of {m['skills_modelled']} skills "
                f"({m['pct_beating_baseline']}%). Mean absolute error "
                f"{m['mean_prophet_mae']:.3f} vs {m['mean_naive_mae']:.3f} "
                f"percentage points -- "
                + (
                    "a real but small improvement. On 21 noisy monthly "
                    "observations, sophisticated forecasting barely outperforms "
                    "assuming next month looks like last month."
                    if better
                    else "the naive baseline is at least as good. The forecasts "
                    "should be read as context, not prediction."
                )
            ),
        )

    skills = store.skills
    top = skills.nlargest(10, "overall_pct")
    rising = skills[skills["direction"] == "rising"].nlargest(8, "change_pts")
    declining = skills[skills["direction"] == "declining"].nsmallest(8, "change_pts")

    return Summary(
        total_postings=store.total_postings(),
        skills_tracked=int(len(skills)),
        categories=int(skills["category"].nunique()),
        date_range_start=d_start,
        date_range_end=d_end,
        extraction_hit_rate_pct=store.extraction["hit_rate_pct"],
        baseline_hit_rate_pct=store.extraction["baseline_hit_rate_pct"],
        data_quality=quality,
        model_quality=model,
        top_skills=[row_to_summary(r) for _, r in top.iterrows()],
        rising_skills=[row_to_summary(r) for _, r in rising.iterrows()],
        declining_skills=[row_to_summary(r) for _, r in declining.iterrows()],
    )
