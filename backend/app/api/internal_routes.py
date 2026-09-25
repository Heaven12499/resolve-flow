import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.config import settings
from app.internal_schemas import CaseAnalysisRequest, CaseAnalysisResult
from app.services.snapshot_analysis import analyze_case_snapshot


router = APIRouter(prefix="/internal/v1", tags=["internal-ai"])


def require_internal_token(x_internal_token: str | None = Header(default=None)) -> None:
    expected = settings.internal_api_token
    if not x_internal_token or not secrets.compare_digest(x_internal_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid internal service token",
        )


@router.post("/ai/analyze", response_model=CaseAnalysisResult)
def analyze_case(
    payload: CaseAnalysisRequest,
    _: None = Depends(require_internal_token),
) -> CaseAnalysisResult:
    return analyze_case_snapshot(payload)
