import { useEffect, useState } from "react";

// Where the FastAPI backend lives. In Phase 10 this moves into
// src/services/api.js so it's defined in exactly one place.
const API_BASE = "http://127.0.0.1:8000";

export default function App() {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState(null);

  // useEffect with an empty [] runs once, right after the component
  // first appears on screen. That's where you fetch data.
  useEffect(() => {
    fetch(`${API_BASE}/api/health`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(setHealth)
      .catch((err) => setError(err.message));
  }, []);

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6">
      <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-bold text-slate-900">SkillTrend AI</h1>
        <p className="mt-1 text-sm text-slate-500">
          Tech Skill Demand Analysis and Forecasting
        </p>

        <div className="mt-5 rounded-lg bg-slate-100 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Backend status
          </p>

          {error && (
            <p className="mt-2 text-sm text-red-600">Cannot reach API: {error}</p>
          )}

          {!error && !health && (
            <p className="mt-2 text-sm text-slate-500">Checking…</p>
          )}

          {health && (
            <pre className="mt-2 text-sm text-emerald-700">
              {JSON.stringify(health, null, 2)}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}