"""FastAPI application entrypoint.

Wires together routers, exception handlers, CORS, and database setup
for the competitive analysis backend.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    health,
    graph,
    knowledge,
    metrics,
    projects,
    reports,
    search,
    sources,
    traces,
)
from app.core.errors import AppError, NotFoundError
from app.core.logging import get_logger, setup_logging
from app.db import models
from app.db.session import engine
from app.services.screenshot_service import artifact_root

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    models.Base.metadata.create_all(bind=engine)
    logger.info("Backend started; database tables ensured.")
    yield


app = FastAPI(title="Competitive Analysis API", lifespan=lifespan)

_origins_env = os.getenv("FRONTEND_ORIGINS", "*").strip()
if _origins_env == "*":
    _allow_origins = ["*"]
    _allow_credentials = False
else:
    _allow_origins = [o.strip() for o in _origins_env.split(",") if o.strip()]
    _allow_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/artifacts", StaticFiles(directory=str(artifact_root())), name="artifacts")


@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError):
    return JSONResponse(
        status_code=404,
        content={"error": exc.message},
    )


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message},
    )


app.include_router(health.router, prefix="/api")
app.include_router(graph.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(traces.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(sources.router, prefix="/api")
app.include_router(knowledge.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(metrics.router, prefix="/api")
