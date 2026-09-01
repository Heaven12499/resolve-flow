"""Deterministic, business-oriented checks for the current RAG index."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models import KnowledgeEvaluationRun
from app.services.knowledge_service import retrieve_knowledge


@dataclass(frozen=True)
class EvaluationCase:
    query: str
    expected_document: str
    category: str


EVALUATION_CASES = (
    EvaluationCase("快递晚了三天，能给补偿吗", "物流延迟补偿规范", "logistics"),
    EvaluationCase("物流已经三天没有更新了怎么办", "物流停滞与异常天气说明", "logistics"),
    EvaluationCase("商家显示发货了但是一直没有揽收", "发货与揽收异常处理规范", "logistics"),
    EvaluationCase("耳机颜色和商品页面不一样，我要退款", "货不对板与错发漏发处理规范", "after_sales"),
    EvaluationCase("商品到手就是坏的，退款需要什么材料", "售后证据收集清单", "after_sales"),
    EvaluationCase("客服机器人能直接给我退款吗", "退款时效与主管复核规范", "after_sales"),
)


def run_rag_evaluation(db: Session) -> KnowledgeEvaluationRun:
    details: list[dict[str, Any]] = []
    hit_cases = 0
    low_confidence_cases = 0
    for case in EVALUATION_CASES:
        sources = retrieve_knowledge(db, case.query, limit=3, category=case.category)
        titles = [source.title for source in sources]
        top_score = sources[0].score if sources else None
        matched = case.expected_document in titles
        hit_cases += int(matched)
        low_confidence_cases += int(top_score is None or top_score < 0.25)
        details.append(
            {
                "query": case.query,
                "expected_document": case.expected_document,
                "matched": matched,
                "top_score": round(top_score, 4) if top_score is not None else None,
                "retrieved_documents": titles,
            }
        )
    run = KnowledgeEvaluationRun(
        total_cases=len(EVALUATION_CASES),
        hit_cases=hit_cases,
        low_confidence_cases=low_confidence_cases,
        recall_at_3=round(hit_cases / len(EVALUATION_CASES), 4),
        details=details,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run
