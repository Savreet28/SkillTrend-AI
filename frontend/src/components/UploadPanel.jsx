import { useRef, useState } from "react";

import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import { ErrorBox, QualityNote } from "./ui";

/**
 * Upload a CSV of job postings and use it as the forecast source.
 *
 * `onDataset` is called with the upload summary (or null when cleared) so
 * the parent can re-fetch forecasts against it.
 */
export default function UploadPanel({ dataset, onDataset }) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState("append");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const inputRef = useRef(null);

  const limits = useApi(() => api.uploadLimits(), []);

  async function handleFile(file) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      onDataset(await api.upload(file, { mode }));
      setOpen(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  if (dataset) {
    return (
      <div className="rounded-xl border border-blue-200 bg-blue-50 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-sm font-semibold text-blue-900">
              Using your data: {dataset.filename}
            </p>
            <p className="text-xs text-blue-800">
              {dataset.rows_used.toLocaleString()} postings ·{" "}
              {dataset.own_months} months ({dataset.own_range[0]} →{" "}
              {dataset.own_range[1]}) · forecasts run from{" "}
              <strong>{dataset.forecast_origin}</strong> ·{" "}
              {dataset.hit_rate_pct}% matched a known skill
            </p>
          </div>
          <button
            onClick={() => onDataset(null)}
            className="rounded-md border border-blue-300 bg-white px-3 py-1.5 text-xs font-medium text-blue-900"
          >
            Back to default corpus
          </button>
        </div>

        {!dataset.can_forecast && (
          <p className="mt-2 rounded bg-amber-100 p-2 text-xs text-amber-900">
            <strong>No forecast produced.</strong>{" "}
            {dataset.forecast_refused_because}
          </p>
        )}
        {dataset.join_month && (
          <p className="mt-2 text-xs text-blue-800">
            <strong>Spliced at {dataset.join_month}.</strong> {dataset.caveat}
          </p>
        )}
        {dataset.rows_dropped &&
          (dataset.rows_dropped.bad_dates > 0 ||
            dataset.rows_dropped.short_text > 0) && (
            <p className="mt-1 text-xs text-blue-700">
              Dropped {dataset.rows_dropped.bad_dates} rows with unreadable
              dates and {dataset.rows_dropped.short_text} with very short text.
            </p>
          )}
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold">Forecast from your own data</p>
          <p className="text-xs text-slate-500">
            Upload a CSV of job postings to move the forecast origin to your
            latest month.
          </p>
        </div>
        <button
          onClick={() => setOpen(!open)}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium hover:border-slate-900"
        >
          {open ? "Cancel" : "Upload CSV"}
        </button>
      </div>

      {open && (
        <div className="mt-3 border-t border-slate-100 pt-3">
          <div className="flex flex-wrap gap-4">
            <label className="flex items-start gap-2 text-xs">
              <input
                type="radio"
                checked={mode === "append"}
                onChange={() => setMode("append")}
                className="mt-0.5"
              />
              <span>
                <strong>Append</strong> — splice onto the historical corpus.
                Forecast origin moves to your latest month.
              </span>
            </label>
            <label className="flex items-start gap-2 text-xs">
              <input
                type="radio"
                checked={mode === "standalone"}
                onChange={() => setMode("standalone")}
                className="mt-0.5"
              />
              <span>
                <strong>Standalone</strong> — your file alone. Needs ≥ 12 months
                to forecast.
              </span>
            </label>
          </div>

          <input
            ref={inputRef}
            type="file"
            accept=".csv,text/csv"
            disabled={busy}
            onChange={(e) => handleFile(e.target.files?.[0])}
            className="mt-3 block w-full text-xs file:mr-3 file:rounded-md file:border-0 file:bg-slate-900 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-white"
          />

          {busy && (
            <p className="mt-2 text-xs text-slate-500">
              Extracting skills… this takes a few seconds.
            </p>
          )}
          {error && (
            <div className="mt-2">
              <ErrorBox message={error} />
            </div>
          )}

          {limits.data && (
            <div className="mt-3">
              <QualityNote>
                Needs a <strong>date</strong> column and a{" "}
                <strong>job-description</strong> column — names are
                auto-detected (anything like <code>posted_date</code>,{" "}
                <code>description</code>). Limits: {limits.data.max_mb} MB,{" "}
                {limits.data.max_rows.toLocaleString()} rows. Your file is
                processed locally by this API and never sent anywhere else.
              </QualityNote>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
