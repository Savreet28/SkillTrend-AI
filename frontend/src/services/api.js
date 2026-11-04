/**
 * Every call to the backend goes through this file.
 *
 * Why centralise: the base URL is defined once, error handling is
 * identical everywhere, and if the API moves, one line changes.
 */

const API_BASE = "http://127.0.0.1:8000/api";

async function request(path) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`);
  } catch {
    // fetch only rejects on network failure, not on 4xx/5xx
    throw new Error("Cannot reach the API. Is the backend running on port 8000?");
  }

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch {
      /* response wasn't JSON; keep the status code */
    }
    throw new Error(detail);
  }

  return response.json();
}

// Skill names can contain /, # and + (CI/CD, C#, C++), so always encode.
const enc = (s) => encodeURIComponent(s);

export const api = {
  health: () => request("/health"),
  summary: () => request("/summary"),
  categories: () => request("/categories"),

  skills: ({ category, q, direction, sort, limit = 200 } = {}) => {
    const params = new URLSearchParams();
    if (category) params.set("category", category);
    if (q) params.set("q", q);
    if (direction) params.set("direction", direction);
    if (sort) params.set("sort", sort);
    params.set("limit", String(limit));
    return request(`/skills?${params}`);
  },

  skill: (name) => request(`/skills/${enc(name)}`),

  trends: (names, { analysisOnly = false } = {}) => {
    const params = new URLSearchParams({ skills: names.join(",") });
    if (analysisOnly) params.set("analysis_only", "true");
    return request(`/trends?${params}`);
  },

  topMovers: (direction, limit = 10) =>
    request(`/trends/top?direction=${direction}&limit=${limit}`),

  forecast: (name) => request(`/forecast/${enc(name)}`),

  // --- Role comparison (live feed, a different data source) ---
  liveStatus: () => request("/live/status"),
  roles: (top = 10) => request(`/roles?top=${top}`),
  role: (name, { sort = "demand_pct", top = 25 } = {}) =>
    request(`/roles/${enc(name)}?sort=${sort}&top=${top}`),
  roleMatrix: ({ skills, limit = 15 } = {}) => {
    const params = new URLSearchParams();
    if (skills?.length) params.set("skills", skills.join(","));
    params.set("limit", String(limit));
    return request(`/roles/matrix?${params}`);
  },
};

export const ROLE_COLORS = {
  "Software Engineer": "#2563eb",
  "Data Engineer": "#059669",
  "Data Scientist": "#db2777",
  "Data Analyst": "#7c3aed",
  "Machine Learning Engineer": "#9333ea",
  "DevOps / SRE": "#ea580c",
  "Product Manager": "#0891b2",
  "QA / Test Engineer": "#ca8a04",
  "Security Engineer": "#dc2626",
};

export const CATEGORY_COLORS = {
  "Programming Languages": "#2563eb",
  "Databases & Warehouses": "#0891b2",
  "BI & Visualization": "#7c3aed",
  "Data Engineering & Big Data": "#059669",
  "Cloud Platforms": "#ea580c",
  "AI & Machine Learning": "#db2777",
  "Generative AI": "#9333ea",
  "DevOps & Version Control": "#65a30d",
  "Office & Collaboration": "#64748b",
};

// Distinct, colour-blind-safe series palette for multi-skill charts.
export const SERIES_COLORS = [
  "#2563eb", "#ea580c", "#059669", "#db2777",
  "#7c3aed", "#0891b2", "#ca8a04", "#64748b",
];

export const fmtMonth = (iso) => {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-GB", { month: "short", year: "2-digit" });
};

export const fmtPct = (v, dp = 1) =>
  v === null || v === undefined ? "—" : `${v.toFixed(dp)}%`;
