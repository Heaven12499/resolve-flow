"""Deterministic, business-oriented checks for the current RAG index."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import KnowledgeEvaluationRun
from app.services.knowledge_service import retrieve_knowledge


@dataclass(frozen=True)
class EvaluationCase:
    query: str
    expected_document: str | None
    category: str | None


EVALUATION_CASES = (
    EvaluationCase("快递晚了三天，能给补偿吗", "物流延迟补偿规范", "logistics"),
    EvaluationCase("物流已经三天没有更新了怎么办", "物流停滞与异常天气说明", "logistics"),
    EvaluationCase("商家显示发货了但是一直没有揽收", "发货与揽收异常处理规范", "logistics"),
    EvaluationCase("耳机颜色和商品页面不一样，我要退款", "货不对板与错发漏发处理规范", "after_sales"),
    EvaluationCase("商品到手就是坏的，退款需要什么材料", "售后证据收集清单", "after_sales"),
    EvaluationCase("客服机器人能直接给我退款吗", "退款时效与主管复核规范", "after_sales"),
    EvaluationCase("包裹到哪个物流节点了", "物流状态说明", "logistics"),
    EvaluationCase("发货两天还没揽收，怎么处理", "发货与揽收异常处理规范", "logistics"),
    EvaluationCase("恶劣天气导致快递一直不动", "物流停滞与异常天气说明", "logistics"),
    EvaluationCase("延迟送达可以申请五元优惠券吗", "优惠券补偿审批边界", "logistics"),
    EvaluationCase("商品破损了，退款前需要上传什么", "售后证据收集清单", "after_sales"),
    EvaluationCase("收到的颜色发错了，售后怎么处理", "货不对板与错发漏发处理规范", "after_sales"),
    EvaluationCase("怀疑商品是假货，能否直接退款", "商品质量问题与退款复核规范", "after_sales"),
    EvaluationCase("退款到账需要主管处理吗", "退款时效与主管复核规范", "after_sales"),
    EvaluationCase("我想修改收货地址", None, None),
    EvaluationCase("怎么申请电子发票", None, None),
    EvaluationCase("会员积分什么时候到账", None, None),
)


def run_rag_evaluation(db: Session) -> KnowledgeEvaluationRun:
    details: list[dict[str, Any]] = []
    hit_cases = 0
    hit_at_1_cases = 0
    low_confidence_cases = 0
    reciprocal_rank_sum = 0.0
    positive_cases = 0
    no_answer_cases = 0
    correct_rejection_cases = 0
    for case in EVALUATION_CASES:
        sources = retrieve_knowledge(db, case.query, limit=3, category=case.category)
        titles = [source.title for source in sources]
        top_score = sources[0].score if sources else None
        if case.expected_document is None:
            no_answer_cases += 1
            correct_rejection_cases += int(not sources)
            matched = not sources
            rank = None
        else:
            positive_cases += 1
            rank = titles.index(case.expected_document) + 1 if case.expected_document in titles else None
            matched = rank is not None
            hit_cases += int(matched)
            hit_at_1_cases += int(rank == 1)
            reciprocal_rank_sum += 1 / rank if rank else 0.0
            low_confidence_cases += int(
                top_score is None or top_score < settings.rag_min_score
            )
        details.append(
            {
                "query": case.query,
                "expected_document": case.expected_document,
                "matched": matched,
                "rank": rank,
                "top_score": round(top_score, 4) if top_score is not None else None,
                "retrieved_documents": titles,
            }
        )
    run = KnowledgeEvaluationRun(
        total_cases=len(EVALUATION_CASES),
        hit_cases=hit_cases,
        low_confidence_cases=low_confidence_cases,
        recall_at_1=round(hit_at_1_cases / positive_cases, 4) if positive_cases else 0.0,
        recall_at_3=round(hit_cases / positive_cases, 4) if positive_cases else 0.0,
        mrr=round(reciprocal_rank_sum / positive_cases, 4) if positive_cases else 0.0,
        no_answer_cases=no_answer_cases,
        correct_rejection_cases=correct_rejection_cases,
        details=details,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run
