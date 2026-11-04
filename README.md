# SkillTrend AI

**What should I learn next — and what am I wasting time on?**

Analyses 58,276 real job postings to tell you which tools in your stack are
redundant, which skills you're missing, and where demand is heading. Every
recommendation shows the numbers behind it.

```
Python · pandas · spaCy · Prophet · FastAPI   |   React · Vite · Tailwind · Recharts
```

Open source, runs locally, no API keys, nothing paid.

---

## What it tells you

Give it a stack:

```
Tableau · Power BI · Python · SQL
```

It answers:

> **REDUNDANT** — You have 2 tools that do the same job: Tableau, Power BI
> Keep **Power BI**: 27.5% of historical postings, 1.7% of current ones, rising
> (+2.02p). Dropping Tableau frees up time without costing you coverage.
>
> **MISSING** — 5 skills commonly paired with your stack
> **Statistical Analysis** in 52% of postings that want Python · **R** in 51% ·
> **Microsoft Excel** in 46% of postings that want Power BI
>
> **DECLINING** — nothing in your stack is on the way out

### Four pages

| Page | Question |
|---|---|
| **Decide** | What should I learn, and what's redundant? |
| **Forecast** | Where is this skill heading? *(plus: upload your own data)* |
| **Roles** | What does my target role actually want? |
| **Method** | How does this work, and where does it fail? |

---

## The finding that shaped the design

**I tried to detect substitutes statistically. It failed, and the failure is
documented in the code.**

The hypothesis: substitutes *repel* — employers want Tableau **or** Power BI,
so they should co-occur below chance. Job ads do the opposite. They write
*"experience with Tableau, Power BI or Looker"*, so alternatives co-occur
constantly.

Measured on known pairs:

| | similarity | lift | Jaccard | asymmetry |
|---|---|---|---|---|
| Known **substitutes** | 0.77 | 11.7 | 0.23 | 0.27 |
| Known **complements** | 0.93 | 23.5 | **0.21** | 0.47 |

TensorFlow/PyTorch (alternatives) scores 0.96 / 57. Docker/Kubernetes
(partners) scores 0.97 / 69. **Statistically identical.** The difference is
semantic — what the tools *do* — which co-occurrence cannot observe.

So the problem was split along what each method can actually do:

| Question | Method |
|---|---|
| "Are these alternatives?" | **Curated** — `skills/substitutes.yaml`, with the evidence above in its header |
| "Which one should I pick?" | **Data** — demand, trend, forecast, stack fit |
| "What am I missing?" | **Data** — co-occurrence (validated 6/6 complements, 3/3 unrelated) |

Validation lives in `scripts/09_cooccurrence.py` and runs every time.

### A second correction

Ranking family members on the historical corpus alone produced *bad advice*:
"learn Oracle", "learn SAS", "learn Informatica". Those are accurate **about
that corpus** — 2022–24 data-analyst postings, heavy on legacy enterprise
tooling — and wrong as guidance for 2026.

Blending in the live multi-role feed fixed it:

| Family | History only | Blended |
|---|---|---|
| Relational database | ❌ Oracle | ✅ **PostgreSQL** |
| Deep learning | ❌ TensorFlow *(coin-flip tie)* | ✅ **PyTorch** |
| ETL tooling | ❌ Informatica | ✅ **Fivetran** |

And where the two corpora disagree, it says so:

> ⚠ *Oracle ranks #1 in the 2022-24 corpus but #3 in current postings
> (7.2% then, 1.0% now)*

---

## Three data sources, never mixed

| | **Historical** | **Live** | **Your upload** |
|---|---|---|---|
| Source | Kaggle (lukebarousse) | 3 job-board APIs | your CSV |
| Size | 58,276 postings | ~4,500, growing monthly | whatever you bring |
| Span | Nov 2022 – Jul 2024 | Nov 2026 → | yours |
| Roles | Data analyst only | 9 role families | yours |
| Powers | trends, forecasts, co-occurrence | role comparison, current demand | your own forecast |

Mixing them would produce numbers describing nobody, so every response says
which source it came from.

---

## Pipeline

Runs offline, writes Parquet. The API only reads.

```
data/raw/gsearch_jobs.csv  (276 MB, 61,953 postings)
  01_load.py          inspect schema, dates, nulls  →  the Data Gate
  02_clean.py         dedupe · dates · text         →  58,276 usable
  03_extract.py       spaCy PhraseMatcher, 120 skills
  04_aggregate.py     skill × month as % · month-quality gate
  05_trends.py        rolling averages · rising/declining
  06_forecast.py      Prophet + naive baseline backtest
  09_cooccurrence.py  PPMI skill graph + the validation above
  10_relations.py     curated families + data-driven ranking

Live track (monthly, scheduled):
  07_fetch_live.py    Arbeitnow · Jobicy · Remotive  →  live_postings.parquet
  08_roles.py         title → role, skills → role profiles
```

### Why percentages, not counts

Monthly posting volume swings from 3,646 down to 272. Raw counts would show
every skill collapsing in late 2024 when only the data collection changed.

### Why a dictionary, not an LLM

Deterministic, auditable, free, and 20 seconds over 58,000 documents. Regex was
rejected because `\b` breaks on `C++`, `C#` and `CI/CD`; PhraseMatcher
tokenises patterns and text identically.

**Result: 82.2% hit rate vs 78.6% for the dataset's own labels — with a
*smaller* vocabulary (120 terms vs 134).**

---

## Running it

**Requirements:** Python 3.10+, Node 18+, a free [Kaggle](https://www.kaggle.com) account.

```bash
git clone <your-repo-url> && cd SkillTrend-AI
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Get the data

```bash
chmod 600 ~/.kaggle/kaggle.json
kaggle datasets download -d lukebarousse/data-analyst-job-postings-google-search \
  -f gsearch_jobs.csv -p data/raw --unzip
```

### Run the pipeline

```bash
python scripts/01_load.py        # inspect only
python scripts/02_clean.py       # ~1 min
python scripts/03_extract.py     # ~20 sec
python scripts/04_aggregate.py && python scripts/05_trends.py
python scripts/06_forecast.py    # ~3 min, 88 Prophet models
python scripts/09_cooccurrence.py && python scripts/10_relations.py
```

Optional — the live multi-role feed (no API key needed):

```bash
python scripts/07_fetch_live.py && python scripts/08_roles.py
```

### Run the app

```bash
cd backend && uvicorn app.main:app --reload     # :8000
cd frontend && npm install && npm run dev       # :5173
```

Dashboard `http://localhost:5173` · API docs `http://127.0.0.1:8000/docs`

### Tests

```bash
python scripts/test_extractor.py   #  8 cases — skill extraction
python scripts/test_roles.py       # 26 cases — role classification
```

---

## Deploying

**The serving artifacts are committed** (~440 KB), so a deployed instance
clones and starts — no pipeline run, no raw data download, no database.

### Backend

`render.yaml` is ready for Render's free tier. Or any host:

```bash
pip install -r backend/requirements.txt
cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

**`backend/requirements.txt` deliberately omits Prophet** — it's ~400 MB with
its Stan binary, more than free tiers comfortably take. Batch forecasts are
precomputed and committed, so the server doesn't need it. On-demand forecasts
(uploads) fall back to an OLS trend **and say so in the response**. On this
data the fallback scores MAE 1.8154 against Prophet's 1.8124 — practically
identical, which is itself consistent with the baseline finding below.

Set `SKILLTREND_CORS_ORIGINS` to your frontend URL. No code change needed.

### Frontend

```bash
cd frontend && npm run build        # → dist/
```

`vercel.json` and `public/_redirects` are included so React Router paths don't
404 on a static host. Set `VITE_API_URL` to your deployed API.

⚠️ Uploads write to `data/uploads/`, which is ephemeral on free tiers — fine,
since uploads are transient, but they won't survive a restart.

---

## API

| Endpoint | Returns |
|---|---|
| `GET /api/health` | liveness, data status, which forecasting model is active |
| `GET /api/summary` | headline stats + data-quality report |
| `GET /api/skills` | searchable skill list |
| `GET /api/trends?skills=…` | monthly series, up to 8 skills |
| `GET /api/forecast/{skill}?dataset=` | history + forecast + **backtest metrics** |
| `GET /api/families` | substitute families with a recommended member |
| `GET /api/related/{skill}` | substitutes + complements, scored |
| `POST /api/stack/analyse` | your stack → verdicts with evidence |
| `POST /api/upload` | CSV in → analysed dataset |
| `GET /api/roles` · `/api/roles/matrix` · `/api/roles/{role}` | role profiles |
| `GET /api/live/status` | live-feed freshness |

Every forecast response carries its own accuracy metrics, so the UI cannot draw
a prediction without the evidence for trusting it.

---

## Limitations

- **One role in the historical data.** Every posting is a data-analyst ad, so
  gap advice is strongest for data tooling and weakest for web/DevOps. The
  dataset was chosen for its 29 months of continuous history; broader datasets
  had only 6–9 months, which cannot support forecasting.
- **Substitute families are human-curated**, because the data provably couldn't
  derive them. The page says so, with the numbers.
- **Forecasts barely beat a naive baseline** — Prophet wins on 53% of skills,
  MAE 0.783 vs 0.811. Every forecast reports its own result, including losses.
- **Role profiles are small.** Software Engineer has ~790 postings; Data
  Analyst has 37. Under 100 is flagged low-confidence, under 30 is dropped.
- **~70% of the live feed isn't tech.** Arbeitnow is a general job board; those
  are classified `Other` and excluded.
- **Uploads under 12 months get no forecast** — refused with a reason, not
  silently faked.
- **A dictionary can't find what it doesn't list.** A skill absent from the 120
  reads as 0%, indistinguishable from unwanted.

## Possible next steps

- Fine-tune a transformer NER using the dictionary as a weak-supervision
  labeller; compare F1 against the rule-based baseline
- Add Adzuna to widen the live feed beyond remote/European roles
- Once ~12 months of live data accumulate, extend trends to the role dimension

---

## Layout

```
backend/app/
  main.py                  app + CORS + routers only
  core/config.py           every path; CORS origins from env
  services/
    data_store.py          loads Parquet once at boot
    advisor.py             the Decide logic
    forecast_service.py    on-demand fit, Prophet optional
    upload_service.py      validate → clean → extract → merge
    extraction.py          shares the pipeline's SkillExtractor
  api/routes/              summary · skills · trends · forecast · roles · stack · upload
frontend/src/
  pages/                   Decide · Forecast · Roles · About
  components/              Layout · UploadPanel · ui
  services/api.js          every backend call; VITE_API_URL aware
scripts/                   01→10 pipeline, extractor, role classifier, tests
skills/
  skills.yaml              120 skills, aliases, ambiguity rules
  substitutes.yaml         curated families + why they're curated
data/
  raw/ processed/          gitignored (large, regenerable)
  live/                    COMMITTED — cannot be regenerated
  uploads/                 gitignored, transient
.github/workflows/         monthly live fetch
render.yaml                backend deploy
```

**Data:** [Data Analyst Job Postings](https://www.kaggle.com/datasets/lukebarousse/data-analyst-job-postings-google-search)
by Luke Barousse · live feed from Arbeitnow, Jobicy and Remotive.
