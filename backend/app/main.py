"""FastAPI application entrypoint.

Wires together routers, exception handlers, CORS, and database setup
for the competitive analysis backend.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    health,
    knowledge,
    projects,
    reports,
    sources,
    traces,
)
from app.core.errors import AppError, NotFoundError
from app.core.logging import get_logger, setup_logging
from app.db import models
from app.db.session import engine

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    models.Base.metadata.create_all(bind=engine)
    logger.info("Backend started; database tables ensured.")
    yield


app = FastAPI(title="Competitive Analysis API", lifespan=lifespan)

# CORS for the Next.js frontend. The MVP allows all origins so the demo
# UI can connect from any port; tighten this for production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
app.include_router(projects.router, prefix="/api")
app.include_router(traces.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(sources.router, prefix="/api")
app.include_router(knowledge.router, prefix="/api")
