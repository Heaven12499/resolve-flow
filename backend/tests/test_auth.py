import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from app.core.auth import Actor, authenticate, current_actor, issue_access_token, require_roles
from app.core.config import settings
from app.main import app


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


def test_agent_cannot_approve_coupon_but_supervisor_can(configured_auth) -> None:
    with TestClient(app) as client:
        agent_token = client.post(
            "/api/auth/login", json={"username": "agent", "password": "agent-password"}
        ).json()["access_token"]
        supervisor_token = client.post(
            "/api/auth/login", json={"username": "supervisor", "password": "supervisor-password"}
        ).json()["access_token"]
        agent_headers = {"Authorization": f"Bearer {agent_token}"}
        supervisor_headers = {"Authorization": f"Bearer {supervisor_token}"}

        created = client.post(
            "/api/tickets",
            json={"order_no": "RF202608290001", "content": "快递晚了三天，能赔偿我吗？"},
            headers=agent_headers,
        ).json()
        denied = client.post(
            f"/api/tickets/{created['id']}/approve-coupon", headers=agent_headers
        )
        assert denied.status_code == 403

        approved = client.post(
            f"/api/tickets/{created['id']}/approve-coupon", headers=supervisor_headers
        )
        assert approved.status_code == 200
        assert approved.json()["approval_tasks"][0]["decision_data"]["approved_by"] == "supervisor"
