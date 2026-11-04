"""SkillTrend AI — FastAPI application entry point.

This file does three things and nothing else:
  1. Creates the FastAPI app
  2. Configures CORS so the React frontend may call it
  3. Registers routers

All real logic lives in services/ (data loading), schemas/ (contracts)
and api/routes/ (endpoints). Keeping main.py thin is what stops a
FastAPI project turning into one giant unreadable file.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import forecast, roles, skills, summary, trends
from app.core import config
from app.schemas.models import Health
from app.services.data_store import get_store

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Load the Parquet files once, at boot, rather than on first request."""
    store = get_store()
    if store.loaded:
        print(f"[data] loaded {len(store.skills)} skills, "
              f"{store.monthly['month'].nunique()} months, "
              f"{len(store.forecasts):,} forecast rows")
    else:
        print(f"[data] FAILED TO LOAD: {store.load_error}")
    yield


app = FastAPI(
    lifespan=lifespan,
    title=config.API_TITLE,
    description=config.API_DESCRIPTION,
    version=config.API_VERSION,
)

# The React dev server runs on a different port than this API. Browsers
# block cross-port requests by default (the "same-origin policy"), so we
# explicitly allow the dev server's origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=Health, tags=["meta"])
def health_check() -> Health:
    """Liveness check that also reports whether the data files loaded."""
    store = get_store()
    return Health(
        status="ok" if store.loaded else "degraded",
        service="SkillTrend AI",
        data_loaded=store.loaded,
        error=store.load_error,
    )


app.include_router(summary.router, prefix="/api")
app.include_router(skills.router, prefix="/api")
app.include_router(trends.router, prefix="/api")
app.include_router(forecast.router, prefix="/api")
app.include_router(roles.router, prefix="/api")
