"""Small, dependency-free authentication boundary for the operations API."""

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings


bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Actor:
    username: str
    role: str


def _encode_segment(value: dict[str, object]) -> str:
    raw = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode_segment(value: str) -> dict[str, object]:
    padding = "=" * (-len(value) % 4)
    decoded = base64.urlsafe_b64decode((value + padding).encode("ascii"))
    payload = json.loads(decoded)
    if not isinstance(payload, dict):
        raise ValueError("invalid token payload")
    return payload


def _secret() -> bytes:
    if not settings.auth_secret:
        raise HTTPException(status_code=503, detail="认证服务未完成密钥配置")
    return settings.auth_secret.encode("utf-8")


def issue_access_token(actor: Actor) -> str:
    now = int(time.time())
    header = _encode_segment({"alg": "HS256", "typ": "JWT"})
    payload = _encode_segment(
        {
            "sub": actor.username,
            "role": actor.role,
            "iat": now,
            "exp": now + settings.auth_token_ttl_minutes * 60,
        }
    )
    signed = f"{header}.{payload}".encode("ascii")
    signature = hmac.new(_secret(), signed, hashlib.sha256).digest()
    return f"{header}.{payload}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode('ascii')}"


def authenticate(username: str, password: str) -> Actor | None:
    candidates = (
        (settings.auth_admin_username, settings.auth_admin_password, "admin"),
        (settings.auth_supervisor_username, settings.auth_supervisor_password, "supervisor"),
        (settings.auth_agent_username, settings.auth_agent_password, "agent"),
    )
    for configured_username, configured_password, role in candidates:
        if configured_password and hmac.compare_digest(username, configured_username) and hmac.compare_digest(password, configured_password):
            return Actor(username=configured_username, role=role)
    return None


def current_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Actor:
    if not settings.auth_enabled:
        return Actor(username="local_demo", role="admin")
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录", headers={"WWW-Authenticate": "Bearer"})
    try:
        header, payload, signature = credentials.credentials.split(".")
        signed = f"{header}.{payload}".encode("ascii")
        expected = hmac.new(_secret(), signed, hashlib.sha256).digest()
        supplied = base64.urlsafe_b64decode((signature + "=" * (-len(signature) % 4)).encode("ascii"))
        claims = _decode_segment(payload)
        username = claims["sub"]
        role = claims["role"]
        expires_at = claims["exp"]
        if not hmac.compare_digest(expected, supplied) or not isinstance(username, str) or not isinstance(role, str) or not isinstance(expires_at, int) or expires_at <= time.time():
            raise ValueError("invalid token")
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录凭证无效", headers={"WWW-Authenticate": "Bearer"}) from None
    return Actor(username=username, role=role)


def require_roles(*roles: str) -> Callable[[Actor], Actor]:
    def dependency(actor: Actor = Depends(current_actor)) -> Actor:
        if actor.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号没有此操作权限")
        return actor

    return dependency
