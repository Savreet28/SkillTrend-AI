"""SkillTrend AI — FastAPI application entry point.

This file does three things and nothing else:
  1. Creates the FastAPI app
  2. Configures CORS so the React frontend may call it
  3. Registers routes

Real logic (data loading, trends, forecasting) lives in other modules
and gets imported here. Keeping main.py thin is what stops a FastAPI
project from turning into one giant unreadable file.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="SkillTrend AI API",
    description="Tech skill demand analysis and forecasting",
    version="0.1.0",
)

# The React dev server runs on a different port than this API.
# Browsers block cross-port requests by default (the "same-origin policy").
# CORS middleware tells the browser these origins are allowed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check() -> dict:
    """Confirm the API is alive.

    Later this will also report whether the processed data files
    loaded successfully at startup.
    """
    return {"status": "ok", "service": "SkillTrend AI", "data_loaded": False}