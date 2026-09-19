# SkillTrend AI

Tech skill demand analysis and forecasting from historical job postings.

Analyses job-posting data to find which technical skills are most in demand,
how that demand shifts month over month, which skills are rising or declining,
and what a time-series model forecasts for the next 6 months.

## Stack

- **Backend:** Python, FastAPI, pandas
- **NLP:** spaCy (dictionary-based skill extraction)
- **ML:** Prophet (time-series forecasting)
- **Frontend:** React, Vite, Tailwind CSS, Recharts

## Status

🚧 In development — Phase 1 of 12 complete (project skeleton).

## Local setup

**Backend**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd backend && uvicorn app.main:app --reload