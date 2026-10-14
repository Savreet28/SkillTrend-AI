# SkillTrend AI

**Skill demand analysis and forecasting over 58,276 data-analyst job postings (Nov 2022 – Apr 2025).**

Extracts technical skills from raw job-description text, measures how demand for each
skill moved month by month, and forecasts six months ahead — with every claim checked
against a baseline and every weakness stated out loud.

```
Python · pandas · spaCy · Prophet · FastAPI   |   React · Vite · Tailwind · Recharts
```

Everything is open source and runs locally. No paid services, no API keys.

---

## What it found

| | |
|---|---|
| **82.2%** extraction hit rate | vs **78.6%** for the labels shipped with the dataset — using a *smaller* vocabulary (120 terms vs 134) |
| **Generative AI: 0% → 5%** | of postings between Nov 2022 and Jul 2024. The dataset's own labels contain no AI terms at all and structurally cannot see this |
| **8 of 29 months excluded** | an automated data-quality gate caught the scraper truncating descriptions in late 2024 |
| **Prophet beats naive on 53% of skills** | mean absolute error 0.783 vs 0.811 percentage points — a real but small improvement |

### Two findings worth reading the code for

**1. A measurement artifact that looked like a market crash.**
The first trend report showed 29 skills declining and only 2 rising — an apparently
dramatic result. It was false. From late 2024 the scraper began capturing truncated
job descriptions (median ~1,600 characters vs ~3,000 before). Shorter text means
fewer skills matched, so *every* skill's percentage fell at once.
`scripts/04_aggregate.py` now applies an automatic month-quality gate; affected months
are excluded from every conclusion but still drawn on the dashboard, shaded, so the
gap is visible rather than hidden.

**2. Sophisticated forecasting barely beats a trivial baseline.**
Every forecast is backtested against "next month equals last month." Prophet wins on
roughly half the skills, by a small margin. That is the honest answer for 21 noisy
monthly observations, and the dashboard reports it per skill — including the skills
where Prophet *loses*.

---

## Pipeline

Six scripts run offline and write Parquet; the API only reads. Fitting 88 Prophet
models cannot happen inside an HTTP request, so training and serving are separated.

```
data/raw/gsearch_jobs.csv  (276 MB, 61,953 postings)
        │
  01_load.py        inspect schema, date coverage, null rates  →  the Data Gate
        │
  02_clean.py       parse dates · drop 3,177 duplicates · drop 500 stubs
        │                                      →  clean_postings.parquet  (58,276)
  03_extract.py     spaCy PhraseMatcher over 120 skills
        │                                      →  posting_skills.parquet  (256,768)
  04_aggregate.py   skill × month as % of postings · month-quality gate
        │                                      →  monthly_demand.parquet
  05_trends.py      rolling averages · period comparison · direction
        │                                      →  skill_trends.parquet
  06_forecast.py    Prophet + naive baseline backtest
                                               →  forecasts.parquet + model_metrics.json
        │
   FastAPI  (loads Parquet once at startup)  →  React dashboard
```

### Why percentages, not counts

Monthly posting volume swings from 3,646 down to 272. Raw counts would show every
skill collapsing in late 2024 when only the data collection changed. Each skill is
measured as a share of *that month's* postings, so the denominator moves with the
numerator.

### Why a dictionary, not an LLM

Skill extraction uses spaCy's `PhraseMatcher` over a curated YAML dictionary. It is
deterministic, auditable (you can point at exactly why a skill was counted), free, and
runs in 20 seconds over 58,000 documents.

Regex was rejected because `\b` word boundaries break on `C++`, `C#` and `CI/CD`.
PhraseMatcher tokenises patterns and text identically, so they line up.

Three rules keep it precise — see `skills/skills.yaml`:

| Rule | Example |
|---|---|
| **Longest match wins** | `no-sql` tokenises to `no`/`-`/`sql`; without this, NoSQL *and* SQL both match |
| **Some names never match alone** | "Go" is also a verb. The dataset's own labels put Go at 3.77% — above Java — because they matched "go above and beyond" |
| **Context blocklists** | "excel **at** communication" rejected; "advanced Excel skills" kept |

---

## Running it

**Requirements:** Python 3.10+, Node 18+, a free [Kaggle](https://www.kaggle.com) account.

### 1. Setup

```bash
git clone <your-repo-url> && cd SkillTrend-AI
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Get the data

`data/` is gitignored — the raw CSV is 276 MB and every processed file is
regenerable. Put your Kaggle API token at `~/.kaggle/kaggle.json`
(Kaggle → Settings → API → Create New Token), then:

```bash
chmod 600 ~/.kaggle/kaggle.json
kaggle datasets download -d lukebarousse/data-analyst-job-postings-google-search -f gsearch_jobs.csv -p data/raw --unzip
```

### 3. Run the pipeline

```bash
python scripts/01_load.py       # inspect — changes nothing
python scripts/02_clean.py      # ~1 min
python scripts/03_extract.py    # ~20 sec
python scripts/04_aggregate.py
python scripts/05_trends.py
python scripts/06_forecast.py   # ~3 min, fits 88 Prophet models
```

Each script prints a report of what it did and what changed.

### 4. Run the app

Two terminals:

```bash
source .venv/bin/activate && cd backend && uvicorn app.main:app --reload
```
```bash
cd frontend && npm install && npm run dev
```

| | |
|---|---|
| Dashboard | http://localhost:5173 |
| API docs (Swagger) | http://127.0.0.1:8000/docs |

### 5. Tests

```bash
python scripts/test_extractor.py
```

Eight cases covering alias normalisation, punctuation-heavy names (`C++`, `CI/CD`),
and the ambiguity traps (`excel at`, `go above and beyond`).

---

## API

| Endpoint | Returns |
|---|---|
| `GET /api/health` | liveness + whether the data files loaded |
| `GET /api/summary` | everything the dashboard landing page needs, in one call |
| `GET /api/categories` | the 9 categories with distinct-posting coverage |
| `GET /api/skills?category=&q=&direction=&sort=` | searchable skill list |
| `GET /api/skills/{skill}` | one skill's summary |
| `GET /api/trends?skills=Python,SQL` | monthly series for up to 8 skills |
| `GET /api/trends/top?direction=rising` | ranked movers |
| `GET /api/forecast/{skill}` | history + 6-month forecast + **backtest metrics** |

Every forecast response carries its own accuracy metrics, so the UI cannot draw a
prediction without also being handed the evidence for how much to trust it.

---

## Dashboard

| Page | |
|---|---|
| **Dashboard** | headline stats, top skills, rising/declining movers, data-quality note |
| **Skill Explorer** | all 120 skills, filterable by category / direction / name |
| **Compare** | up to 6 skills side by side, with excluded months shaded |
| **Forecast** | history (solid) vs forecast (dashed + uncertainty band), with backtest scores |
| **Method** | how it works and where it falls short |

---

## Limitations

Stated plainly, because a project that says what it does not know is worth more than
one that looks impressive and cannot be defended.

- **One role.** Every posting is a data-analyst ad. Web and DevOps skills barely
  appear — this is not a picture of the whole tech market. The dataset was chosen for
  its 29 months of continuous history; broader datasets had only 6–9 months, which
  cannot support forecasting.
- **One source.** Scraped from Google job search results. Whatever that misses, this misses.
- **Scrape time, not posting time.** The date is when the collector saw the ad.
  Fine at monthly granularity, not exact.
- **A dictionary cannot find what it does not list.** A skill absent from the 120
  terms reads as 0% — indistinguishable from genuinely unwanted.
- **Mentions are not requirements.** "Python a plus" and "expert Python required"
  count identically.
- **Forecasts are weak.** 21 monthly observations is very little history. Yearly
  seasonality is deliberately switched off (1.75 cycles is not enough to fit a yearly
  pattern without fitting noise). Read the forecasts as a direction, not a number.

## Possible next steps

- Fine-tune a transformer NER for skill extraction using the dictionary as a weak
  supervision labeller, and compare F1 against the rule-based baseline
- Add a broader multi-role dataset for skill coverage, keeping forecasts on the
  long-history corpus
- Deploy so the dashboard is reachable without running it locally

---

## Project layout

```
backend/app/
  main.py              FastAPI app, CORS, router registration — nothing else
  core/config.py       every path in one place
  services/            loads Parquet once at startup, serves from memory
  schemas/             Pydantic response models
  api/routes/          summary · skills · trends · forecast
frontend/src/
  services/api.js      every backend call
  hooks/useApi.js      loading / error / data for every page
  components/          Layout + shared UI
  pages/               Dashboard · SkillExplorer · Compare · Forecast · About
scripts/               01_load → 06_forecast, plus skill_extractor + tests
skills/skills.yaml     the 120-skill dictionary with aliases and ambiguity rules
data/                  raw · processed · forecasts   (gitignored, regenerable)
docs/                  phase write-ups
```

**Data:** [Data Analyst Job Postings](https://www.kaggle.com/datasets/lukebarousse/data-analyst-job-postings-google-search)
by Luke Barousse.
