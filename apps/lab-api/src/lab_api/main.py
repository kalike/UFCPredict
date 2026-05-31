"""Lab API — FastAPI entry point, port 8101."""

import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from lab_api.routers import (
    combo_search, compare, dashboard, fighters, hp_search,
    models as models_router, predictions, publish, recalculation, scraping, system,
)

# Prevent OpenMP segfault when PyTorch and LightGBM both load libomp on macOS
os.environ.setdefault("OMP_NUM_THREADS", "1")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle. DataStore is lazy-loaded on first request."""
    yield


app = FastAPI(
    title="UFC Lab API",
    description="Local lab for training, HP search, model management, scraping, publish.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router)
app.include_router(scraping.router)
app.include_router(publish.router)
app.include_router(models_router.router)
app.include_router(hp_search.router)
app.include_router(combo_search.router)
app.include_router(fighters.router)
app.include_router(compare.router)
app.include_router(predictions.router)
app.include_router(recalculation.router)
app.include_router(dashboard.router)


def run():
    """Entry point for `lab-api` script (port 8101)."""
    uvicorn.run("lab_api.main:app", host="0.0.0.0", port=8101, reload=True)


if __name__ == "__main__":
    run()
