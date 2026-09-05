import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import settings
from app.db import Base, SessionLocal, engine
from app.services.demo_data import seed_demo_data
from app.services.knowledge_service import get_embedding_model
from app.services.processing_queue import recover_unfinished_ticket_jobs


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)
    if settings.seed_demo_data:
        with SessionLocal() as db:
            seed_demo_data(db)
    if settings.rag_enabled:
        try:
            # Pay the one-time model load cost before the first live ticket so
            # the demo path does not stall on its first knowledge lookup.
            get_embedding_model()
        except Exception as exc:
            logger.warning("Embedding model warm-up failed; RAG will degrade safely (%s)", type(exc).__name__)
    recover_unfinished_ticket_jobs()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="电商智能工单处置平台的可运行MVP。",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "demo_order_no": "RF202608290001",
    }
