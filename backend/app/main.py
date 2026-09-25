import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.internal_routes import router as internal_router
from app.core.config import settings
from app.core.observability import metrics_response, observe_http_request
from app.db import Base, SessionLocal, engine
from app.services.demo_data import seed_ai_demo_data, seed_demo_data
from app.services.knowledge_service import get_embedding_model
from app.services.processing_queue import recover_unfinished_ticket_jobs


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)
    if settings.seed_demo_data:
        with SessionLocal() as db:
            if settings.legacy_business_api_enabled:
                seed_demo_data(db)
            else:
                seed_ai_demo_data(db)
    if settings.rag_enabled:
        try:
            # Pay the one-time model load cost before the first live ticket so
            # the demo path does not stall on its first knowledge lookup.
            get_embedding_model()
        except Exception as exc:
            logger.warning("Embedding model warm-up failed; RAG will degrade safely (%s)", type(exc).__name__)
    if settings.legacy_business_api_enabled:
        recover_unfinished_ticket_jobs()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="ResolveFlow 独立 AI 分析与知识服务。",
    lifespan=lifespan,
)
app.middleware("http")(observe_http_request)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
)
if settings.legacy_business_api_enabled:
    app.include_router(router)
app.include_router(internal_router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "demo_order_no": "RF202608290001",
    }


@app.get("/health")
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "service": "ai-service",
        "rag_enabled": settings.rag_enabled,
        "legacy_business_api_enabled": settings.legacy_business_api_enabled,
    }


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return metrics_response()
