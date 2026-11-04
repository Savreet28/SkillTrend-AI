"""Forecast a single skill on demand, from any corpus.

WHY ON DEMAND AND NOT ONLY BATCH
06_forecast.py precomputes forecasts for the default corpus, which keeps
page loads instant. But an uploaded dataset has no precomputed anything,
and its forecast origin is wherever the user's data ends. So we also need
to fit one skill at a time, in about a second.

WHY PROPHET IS OPTIONAL
Prophet pulls in cmdstanpy and a compiled Stan binary -- roughly 400 MB,
and a noticeable chunk of RAM at import. Free hosting tiers are
memory-constrained, so the import is lazy and guarded. If Prophet is not
installed, we fall back to an ordinary least-squares trend with an
interval derived from the residuals.

The fallback is NOT presented as equivalent. Every response states which
method produced it, and the backtest runs either way, so the caller can
see whether the thing that actually ran beat a naive baseline.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

logging.getLogger("prophet").setLevel(logging.ERROR)
logging.getLogger("cmdstanpy").setLevel(logging.ERROR)
warnings.filterwarnings("ignore")

HOLDOUT = 3
MIN_MONTHS_TO_FORECAST = 12
INTERVAL_Z = 1.2816          # 80% interval for the fallback


@dataclass
class ForecastResult:
    skill: str
    method: str                       # "prophet" | "linear-trend"
    horizon: int
    history: list[dict] = field(default_factory=list)
    forecast: list[dict] = field(default_factory=list)
    prophet_mae: float | None = None
    naive_mae: float | None = None
    beats_baseline: bool | None = None
    n_observations: int = 0
    origin: date | None = None
    caveat: str = ""


def _prophet_available() -> bool:
    try:
        import prophet  # noqa: F401
        return True
    except Exception:                                   # noqa: BLE001
        return False


def _fit_prophet(history: pd.DataFrame, periods: int) -> pd.DataFrame:
    from prophet import Prophet

    model = Prophet(
        growth="linear",
        # 21 monthly points is 1.75 annual cycles. Fitting a yearly pattern
        # to under two cycles fits noise, so it stays off.
        yearly_seasonality=False,
        weekly_seasonality=False,
        daily_seasonality=False,
        changepoint_prior_scale=0.05,
        interval_width=0.80,
    )
    model.fit(history)
    future = model.make_future_dataframe(periods=periods, freq="MS")
    out = model.predict(future)
    for col in ("yhat", "yhat_lower", "yhat_upper"):
        out[col] = out[col].clip(lower=0.0)
    return out[["ds", "yhat", "yhat_lower", "yhat_upper"]]


def _fit_linear(history: pd.DataFrame, periods: int) -> pd.DataFrame:
    """OLS trend with a residual-based interval. The no-Prophet fallback."""
    y = history["y"].to_numpy(dtype=float)
    x = np.arange(len(y), dtype=float)

    slope, intercept = np.polyfit(x, y, 1)
    fitted = slope * x + intercept
    resid_std = float(np.std(y - fitted, ddof=1)) if len(y) > 2 else 0.0

    future_x = np.arange(len(y) + periods, dtype=float)
    yhat = np.clip(slope * future_x + intercept, 0.0, None)
    margin = INTERVAL_Z * resid_std

    months = pd.date_range(history["ds"].min(), periods=len(future_x), freq="MS")
    return pd.DataFrame({
        "ds": months,
        "yhat": yhat,
        "yhat_lower": np.clip(yhat - margin, 0.0, None),
        "yhat_upper": yhat + margin,
    })


def _mae(actual: np.ndarray, predicted: np.ndarray) -> float:
    return float(np.mean(np.abs(actual - predicted)))


def forecast_skill(
    series: pd.DataFrame,
    skill: str,
    horizon: int = 6,
    prefer_prophet: bool = True,
) -> ForecastResult:
    """Forecast one skill.

    `series` needs columns `month` and `demand_pct`, already filtered to
    analysis-grade rows and sorted.
    """
    series = series.sort_values("month")
    history = pd.DataFrame({
        "ds": pd.to_datetime(series["month"]),
        "y": series["demand_pct"].astype(float),
    }).reset_index(drop=True)

    n = len(history)
    result = ForecastResult(skill=skill, method="none", horizon=horizon,
                            n_observations=n)
    result.history = [
        {"month": d.date(), "actual": round(float(v), 3)}
        for d, v in zip(history["ds"], history["y"])
    ]

    if n < MIN_MONTHS_TO_FORECAST:
        result.caveat = (
            f"Only {n} months of history. A forecast needs at least "
            f"{MIN_MONTHS_TO_FORECAST} to be worth anything, so none was produced."
        )
        return result

    use_prophet = prefer_prophet and _prophet_available()
    fit = _fit_prophet if use_prophet else _fit_linear
    result.method = "prophet" if use_prophet else "linear-trend"

    # ---- Backtest against a naive carry-forward --------------------------
    train, test = history.iloc[:-HOLDOUT], history.iloc[-HOLDOUT:]
    actual = test["y"].to_numpy()

    backtest = fit(train, HOLDOUT)
    model_pred = backtest["yhat"].to_numpy()[-HOLDOUT:]
    naive_pred = np.repeat(train["y"].iloc[-1], HOLDOUT)

    result.prophet_mae = round(_mae(actual, model_pred), 4)
    result.naive_mae = round(_mae(actual, naive_pred), 4)
    result.beats_baseline = result.prophet_mae < result.naive_mae

    # ---- Final fit on everything ------------------------------------------
    full = fit(history, horizon)
    origin = history["ds"].max()
    result.origin = origin.date()

    future = full[full["ds"] > origin]
    result.forecast = [
        {
            "month": r["ds"].date(),
            "yhat": round(float(r["yhat"]), 3),
            "yhat_lower": round(float(r["yhat_lower"]), 3),
            "yhat_upper": round(float(r["yhat_upper"]), 3),
        }
        for _, r in future.iterrows()
    ]

    method_note = (
        "Fitted with Prophet."
        if use_prophet
        else "Prophet is not installed here, so this used an ordinary "
             "least-squares trend with a residual-based interval. It is a "
             "weaker model and the backtest below reflects what actually ran."
    )
    verdict = (
        f"It beat a naive 'next month equals last month' baseline "
        f"(MAE {result.prophet_mae:.2f} vs {result.naive_mae:.2f} percentage "
        f"points on a {HOLDOUT}-month holdout)."
        if result.beats_baseline
        else f"It did NOT beat a naive 'next month equals last month' baseline "
             f"(MAE {result.prophet_mae:.2f} vs {result.naive_mae:.2f}). Treat "
             f"the projection as no more informative than the last observed value."
    )
    result.caveat = f"{method_note} {verdict}"
    return result


def prophet_status() -> dict:
    """Reported by /api/health so the UI can explain which model is in use."""
    available = _prophet_available()
    return {
        "prophet_available": available,
        "forecast_method": "prophet" if available else "linear-trend",
        "note": (
            "Prophet is installed; forecasts use it."
            if available
            else "Prophet is not installed (it is optional — ~400 MB, which "
                 "some free hosting tiers cannot take). Forecasts fall back to "
                 "an OLS trend and say so."
        ),
    }
