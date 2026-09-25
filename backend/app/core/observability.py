import logging
import re
import time
import uuid
from contextvars import ContextVar

from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest


logger = logging.getLogger("resolveflow.requests")
REQUEST_ID_HEADER = "X-Request-Id"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,100}$")
request_id_context: ContextVar[str] = ContextVar("request_id", default="none")

HTTP_REQUESTS = Counter(
    "resolveflow_ai_http_requests_total",
    "HTTP requests handled by the AI service",
    ("method", "route", "status"),
)
HTTP_DURATION = Histogram(
    "resolveflow_ai_http_request_duration_seconds",
    "AI service HTTP request duration",
    ("method", "route"),
)
ANALYSIS_RUNS = Counter(
    "resolveflow_ai_analysis_runs_total",
    "Snapshot analysis requests by terminal outcome",
    ("outcome",),
)
ANALYSIS_DURATION = Histogram(
    "resolveflow_ai_analysis_duration_seconds",
    "Snapshot analysis execution duration",
    ("outcome",),
)


async def observe_http_request(request: Request, call_next):
    supplied = request.headers.get(REQUEST_ID_HEADER)
    request_id = supplied if supplied and _SAFE_REQUEST_ID.fullmatch(supplied) else str(uuid.uuid4())
    token = request_id_context.set(request_id)
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
    finally:
        route = getattr(request.scope.get("route"), "path", "unmatched")
        duration = time.perf_counter() - started
        HTTP_REQUESTS.labels(request.method, route, str(status_code)).inc()
        HTTP_DURATION.labels(request.method, route).observe(duration)
        logger.info(
            "request completed request_id=%s method=%s route=%s status=%s duration_ms=%d",
            request_id,
            request.method,
            route,
            status_code,
            round(duration * 1000),
        )
        request_id_context.reset(token)


def metrics_response() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def record_analysis(outcome: str, duration_seconds: float | None = None) -> None:
    ANALYSIS_RUNS.labels(outcome).inc()
    if duration_seconds is not None:
        ANALYSIS_DURATION.labels(outcome).observe(duration_seconds)
