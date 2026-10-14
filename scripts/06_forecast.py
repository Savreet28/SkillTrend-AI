"""Step 6 of the pipeline: forecast skill demand 6 months ahead.

Input:  data/processed/monthly_trends.parquet
        data/processed/skill_trends.parquet
Output: data/forecasts/forecasts.parquet     (history + forecast, one row per month)
        data/forecasts/model_metrics.json    (per-skill backtest results)

THE RULE THIS SCRIPT ENFORCES: a forecast is only worth showing if it
beats a trivial baseline. The baseline here is "next month looks like
last month" (naive carry-forward). It sounds dumb; on short, noisy
series it is often very hard to beat.

So every skill gets backtested:
  * hold out the final HOLDOUT months
  * fit Prophet on the rest, predict the holdout
  * carry the last training value forward, predict the holdout
  * compare MAE

Skills where Prophet loses are still forecast, but flagged
`beats_baseline = false` and the API passes that to the dashboard. We
report what the model actually does, not what we hoped it would do.

WHY yearly_seasonality IS OFF: there are 21 monthly observations, i.e.
1.75 annual cycles. Fitting a yearly pattern to less than two cycles
means fitting noise. Prophet would happily do it and produce
confident-looking seasonal wiggles with nothing behind them.
"""

from __future__ import annotations

import json
import logging
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from prophet import Prophet

# Prophet/cmdstanpy are extremely chatty on every single fit.
logging.getLogger("prophet").setLevel(logging.ERROR)
logging.getLogger("cmdstanpy").setLevel(logging.ERROR)
warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
MONTHLY_FILE = ROOT / "data" / "processed" / "monthly_trends.parquet"
SUMMARY_FILE = ROOT / "data" / "processed" / "skill_trends.parquet"
OUT_DIR = ROOT / "data" / "forecasts"
OUT_FORECASTS = OUT_DIR / "forecasts.parquet"
OUT_METRICS = OUT_DIR / "model_metrics.json"

HORIZON = 6          # months to forecast
HOLDOUT = 3          # months held out for the backtest
MIN_MEAN_PCT = 0.5   # skills quieter than this are too sparse to forecast
MIN_MONTHS = 12      # minimum observations before we attempt a fit


def fit_prophet(history: pd.DataFrame, periods: int) -> pd.DataFrame:
    """Fit Prophet on (ds, y) and return `periods` future months."""
    model = Prophet(
        growth="linear",
        yearly_seasonality=False,   # see module docstring
        weekly_seasonality=False,
        daily_seasonality=False,
        changepoint_prior_scale=0.05,
        interval_width=0.80,
    )
    model.fit(history)
    future = model.make_future_dataframe(periods=periods, freq="MS")
    out = model.predict(future)
    # Demand is a percentage: it cannot be negative.
    for col in ("yhat", "yhat_lower", "yhat_upper"):
        out[col] = out[col].clip(lower=0.0)
    return out


def mae(actual: np.ndarray, predicted: np.ndarray) -> float:
    return float(np.mean(np.abs(actual - predicted)))


def mape(actual: np.ndarray, predicted: np.ndarray) -> float:
    mask = actual > 0
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100)


def main() -> None:
    if not MONTHLY_FILE.exists():
        raise SystemExit(f"Missing {MONTHLY_FILE}. Run 05_trends.py first.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    monthly = pd.read_parquet(MONTHLY_FILE)
    monthly = monthly[monthly["is_analysis_grade"]].sort_values(["skill", "month"])
    summary = pd.read_parquet(SUMMARY_FILE)

    n_months = monthly["month"].nunique()
    candidates = summary[summary["overall_pct"] >= MIN_MEAN_PCT]["skill"].tolist()

    print("=" * 72)
    print("FORECASTING")
    print("=" * 72)
    print(f"\nHistory          {n_months} analysis-grade months "
          f"({monthly['month'].min():%b %Y} - {monthly['month'].max():%b %Y})")
    print(f"Horizon          {HORIZON} months")
    print(f"Backtest holdout {HOLDOUT} months")
    print(f"Skills to model  {len(candidates)} "
          f"(mean demand >= {MIN_MEAN_PCT}%)\n")

    if n_months < MIN_MONTHS:
        raise SystemExit(f"Only {n_months} months -- refusing to forecast.")

    all_rows: list[pd.DataFrame] = []
    metrics: dict[str, dict] = {}

    for i, skill in enumerate(candidates, start=1):
        series = monthly[monthly["skill"] == skill][["month", "demand_pct"]]
        history = series.rename(columns={"month": "ds", "demand_pct": "y"}).reset_index(drop=True)

        if len(history) < MIN_MONTHS:
            continue

        # ---- Backtest -------------------------------------------------
        train = history.iloc[:-HOLDOUT]
        test = history.iloc[-HOLDOUT:]
        actual = test["y"].to_numpy()

        bt = fit_prophet(train, HOLDOUT)
        prophet_pred = bt["yhat"].to_numpy()[-HOLDOUT:]
        naive_pred = np.repeat(train["y"].iloc[-1], HOLDOUT)

        p_mae, n_mae = mae(actual, prophet_pred), mae(actual, naive_pred)

        metrics[skill] = {
            "prophet_mae": round(p_mae, 4),
            "prophet_mape": round(mape(actual, prophet_pred), 2),
            "naive_mae": round(n_mae, 4),
            "naive_mape": round(mape(actual, naive_pred), 2),
            "beats_baseline": bool(p_mae < n_mae),
            "improvement_pct": round((n_mae - p_mae) / n_mae * 100, 1) if n_mae > 0 else None,
            "n_observations": int(len(history)),
        }

        # ---- Final fit on all data ------------------------------------
        full = fit_prophet(history, HORIZON)
        last_observed = history["ds"].max()

        out = full[["ds", "yhat", "yhat_lower", "yhat_upper"]].copy()
        out["skill"] = skill
        out["is_forecast"] = out["ds"] > last_observed
        out = out.merge(
            history.rename(columns={"y": "actual"}), on="ds", how="left"
        )
        all_rows.append(out)

        if i % 10 == 0 or i == len(candidates):
            print(f"  fitted {i}/{len(candidates)}")

    forecasts = pd.concat(all_rows, ignore_index=True).rename(columns={"ds": "month"})
    forecasts = forecasts[
        ["skill", "month", "actual", "yhat", "yhat_lower", "yhat_upper", "is_forecast"]
    ]
    forecasts.to_parquet(OUT_FORECASTS, index=False)

    # ---- Honest verdict -------------------------------------------------
    wins = sum(m["beats_baseline"] for m in metrics.values())
    total = len(metrics)
    mean_p = float(np.mean([m["prophet_mae"] for m in metrics.values()]))
    mean_n = float(np.mean([m["naive_mae"] for m in metrics.values()]))

    summary_metrics = {
        "horizon_months": HORIZON,
        "holdout_months": HOLDOUT,
        "history_months": int(n_months),
        "skills_modelled": total,
        "skills_beating_baseline": int(wins),
        "pct_beating_baseline": round(wins / total * 100, 1),
        "mean_prophet_mae": round(mean_p, 4),
        "mean_naive_mae": round(mean_n, 4),
        "prophet_better_overall": bool(mean_p < mean_n),
        "per_skill": metrics,
    }
    OUT_METRICS.write_text(json.dumps(summary_metrics, indent=2))

    print("\n" + "=" * 72)
    print("BACKTEST: PROPHET vs NAIVE CARRY-FORWARD")
    print("=" * 72)
    print(f"\nSkills modelled              {total}")
    print(f"Prophet beat the baseline on {wins}  ({wins / total * 100:.0f}%)")
    print(f"\nMean absolute error (percentage points, lower is better)")
    print(f"  Prophet  {mean_p:.3f}")
    print(f"  Naive    {mean_n:.3f}")

    verdict = "Prophet" if mean_p < mean_n else "the naive baseline"
    print(f"\n  -> On average, {verdict} is more accurate on this data.")

    ranked = sorted(metrics.items(), key=lambda kv: kv[1]["prophet_mae"] - kv[1]["naive_mae"])
    print("\n" + "-" * 72)
    print(f"{'skill':<22} {'prophet':>9} {'naive':>9} {'delta':>9}  verdict")
    print("-" * 72)
    for skill, m in ranked[:8]:
        d = m["prophet_mae"] - m["naive_mae"]
        print(f"{skill:<22} {m['prophet_mae']:>9.3f} {m['naive_mae']:>9.3f} "
              f"{d:>+9.3f}  {'Prophet' if d < 0 else 'naive'}")
    print("  ...")
    for skill, m in ranked[-4:]:
        d = m["prophet_mae"] - m["naive_mae"]
        print(f"{skill:<22} {m['prophet_mae']:>9.3f} {m['naive_mae']:>9.3f} "
              f"{d:>+9.3f}  {'Prophet' if d < 0 else 'naive'}")

    print(f"\nWrote {OUT_FORECASTS.relative_to(ROOT)}  ({len(forecasts):,} rows)")
    print(f"Wrote {OUT_METRICS.relative_to(ROOT)}\n")


if __name__ == "__main__":
    main()
