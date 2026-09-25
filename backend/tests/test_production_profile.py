import os
import subprocess
import sys

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_internal_token_requires_minimum_entropy_budget():
    with pytest.raises(ValidationError):
        Settings(internal_api_token="too-short", _env_file=None)


def test_production_profile_does_not_import_legacy_business_router():
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": "sqlite+pysqlite:///:memory:",
            "AUTO_CREATE_TABLES": "false",
            "SEED_DEMO_DATA": "false",
            "LEGACY_BUSINESS_API_ENABLED": "false",
            "RAG_ENABLED": "false",
        }
    )
    code = (
        "import sys; from app.main import app; "
        "assert 'app.api.routes' not in sys.modules; "
        "assert 'app.services.processing_queue' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
