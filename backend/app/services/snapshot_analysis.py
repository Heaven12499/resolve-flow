from sqlalchemy.orm import Session

from app.internal_schemas import (
    CaseAnalysisRequest,
    CaseAnalysisResult,
)
from app.services.snapshot_orchestrator import evidence_references, orchestrate_snapshot


def analyze_case_snapshot(payload: CaseAnalysisRequest, db: Session | None = None) -> CaseAnalysisResult:
    """Analyze an immutable business snapshot without writing business data.

    The Java service remains responsible for validating and applying this
    non-binding recommendation.
    """
    state = orchestrate_snapshot(payload, db)
    classification = state["classification"]
    decision = state["decision"]
    sources = state.get("knowledge_sources", [])

    return CaseAnalysisResult(
        task_id=payload.task_id,
        ticket_id=payload.ticket_id,
        business_version=payload.business_version,
        intent=classification.intent,
        priority=classification.priority,
        risk_level=classification.risk_level,
        recommended_action=decision["recommended_action"],
        suggested_coupon_amount=decision.get("suggested_coupon_amount"),
        reply_draft=state["reply_draft"],
        confidence=0.9 if classification.source != "rules" else 0.75,
        requires_human_approval=decision["requires_human_approval"],
        evidence=evidence_references(payload, sources),
        model_source=classification.source,
        fallback_reason=classification.fallback_reason,
        orchestration_plan=state["plan"],
        execution_trace=state["execution_trace"],
        knowledge_sources=sources,
        review_package=state.get("review_package"),
    )
