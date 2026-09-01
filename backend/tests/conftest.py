import os

import pytest


os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["AUTO_CREATE_TABLES"] = "true"
os.environ["SEED_DEMO_DATA"] = "true"


@pytest.fixture(autouse=True)
def use_rules_by_default(monkeypatch):
    """Keep tests offline even when a developer has configured a real API key."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "ai_provider", "rules")
    monkeypatch.setattr(settings, "deepseek_api_key", None)
    monkeypatch.setattr(settings, "rag_enabled", False)
