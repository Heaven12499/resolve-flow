import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core.auth import Actor, authenticate, current_actor, issue_access_token, require_roles
from app.core.config import settings


@pytest.fixture
def configured_auth(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_secret", "test-signing-secret")
    monkeypatch.setattr(settings, "auth_admin_password", "admin-password")
    monkeypatch.setattr(settings, "auth_supervisor_password", "supervisor-password")
    monkeypatch.setattr(settings, "auth_agent_password", "agent-password")


def test_login_credentials_issue_a_verifiable_actor(configured_auth) -> None:
    actor = authenticate("supervisor", "supervisor-password")

    assert actor == Actor(username="supervisor", role="supervisor")
    token = issue_access_token(actor)
    restored = current_actor(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))

    assert restored == actor


def test_invalid_credentials_and_role_are_rejected(configured_auth) -> None:
    assert authenticate("supervisor", "incorrect") is None

    with pytest.raises(HTTPException) as error:
        require_roles("admin")(Actor(username="agent", role="agent"))

    assert error.value.status_code == 403
