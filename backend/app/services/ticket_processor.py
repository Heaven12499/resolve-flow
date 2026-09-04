import json
import logging
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ApprovalTask, AuditLog, LogisticsEvent, Order, Ticket, TicketMessage
from app.services.knowledge_service import KnowledgeSource, retrieve_knowledge
from app.services.llm_provider import get_provider


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClassificationResult:
    intent: str
    priority: str
    risk_level: str
    suggested_action: str
    source: str = "rules"
    fallback_reason: str | None = None


class DeepSeekClassification(BaseModel):
    intent: Literal[
        "logistics_query",
        "delivery_delay_compensation",
        "refund_risk_review",
        "other",
    ]


class RefundReviewAnalysis(BaseModel):
    """Non-binding analysis for a supervisor's refund review workbench."""

    issue_type: Literal["quality_defect", "wrong_item", "counterfeit", "damage", "refund_request", "other"]
    evidence_completeness: Literal["complete", "partial", "missing"]
    missing_evidence: list[str]
    policy_condition_coverage: Literal["high", "medium", "low"]
    recommended_next_step: Literal["request_evidence", "supervisor_review"]
    summary: str


REFUND_EVIDENCE = ["订单信息", "商品问题照片或视频", "签收及使用情况"]


LOGISTICS_KEYWORDS = ("物流", "快递", "没到", "到哪", "发货", "配送")
COMPENSATION_KEYWORDS = ("赔偿", "补偿", "优惠券", "延迟")
REFUND_RISK_KEYWORDS = ("退款", "质量", "不一样", "假货", "损坏")
ESCALATION_KEYWORDS = ("投诉", "12315", "曝光", "起诉")


def classification_from_intent(
    intent: str, content: str, *, source: str = "rules"
) -> ClassificationResult:
    """The backend, not the model, owns business risk and action mapping."""
    if intent == "refund_risk_review":
        return ClassificationResult(
            intent="refund_risk_review",
            priority="high",
            risk_level="high",
            suggested_action="escalate_to_supervisor",
            source=source,
        )
    if intent == "delivery_delay_compensation":
        return ClassificationResult(
            intent="delivery_delay_compensation",
            priority="medium",
            risk_level="medium",
            suggested_action="request_coupon_approval",
            source=source,
        )
    if intent == "logistics_query":
        return ClassificationResult(
            intent="logistics_query",
            priority=(
                "high"
                if any(keyword in content for keyword in ESCALATION_KEYWORDS)
                else "medium"
            ),
            risk_level="low",
            suggested_action="query_logistics",
            source=source,
        )

    return ClassificationResult(
        intent="other",
        priority="medium",
        risk_level="medium",
        suggested_action="escalate_to_human",
        source=source,
    )


def classify_by_rules(content: str) -> ClassificationResult:
    """Offline baseline and fallback for all LLM failures."""
    if any(keyword in content for keyword in REFUND_RISK_KEYWORDS):
        return classification_from_intent("refund_risk_review", content)
    if any(keyword in content for keyword in COMPENSATION_KEYWORDS):
        return classification_from_intent("delivery_delay_compensation", content)
    if any(keyword in content for keyword in LOGISTICS_KEYWORDS):
        return classification_from_intent("logistics_query", content)
    return classification_from_intent("other", content)


def classify_with_deepseek(content: str) -> ClassificationResult:
    fallback = classify_by_rules(content)
    provider = get_provider("dispatcher")
    if not provider:
        if settings.ai_provider.lower() != "rules":
            return replace(fallback, fallback_reason="llm_provider_unavailable")
        return fallback

    system_prompt = """你是电商客服工单意图分类器。仅返回一个JSON对象，不要Markdown，且只能包含intent字段。
intent只能是以下四个值之一：logistics_query、delivery_delay_compensation、refund_risk_review、other。
物流查询使用logistics_query；用户因物流延迟要求赔偿、补偿或优惠券时使用delivery_delay_compensation；
涉及退款、质量争议、假货或损坏时，必须使用refund_risk_review；其余使用other。"""
    messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"客户工单内容：{content}"},
        ]
    try:
        raw_content = provider.chat(messages, json_mode=True).content
        result = DeepSeekClassification.model_validate(json.loads(raw_content))
        return classification_from_intent(result.intent, content, source=provider.name)
    except (httpx.HTTPError, KeyError, IndexError, TypeError, json.JSONDecodeError, ValidationError) as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        diagnostic = f"http_{status_code}" if status_code else type(exc).__name__
        logger.warning("LLM classification failed; using rules fallback (%s)", diagnostic)
        return replace(fallback, fallback_reason=f"{provider.name}_{diagnostic}")


def classify_ticket(content: str) -> ClassificationResult:
    return classify_with_deepseek(content)


def generate_grounded_reply(
    customer_content: str, draft_reply: str, sources: list[KnowledgeSource]
) -> tuple[str, str]:
    """Use retrieved policy as context, while keeping action decisions in backend code."""
    if not sources:
        return draft_reply, "template"
    provider = get_provider("reply")
    if not provider:
        return draft_reply, "template"

    policy_context = "\n\n".join(
        f"【{source.title} {source.version}】\n{source.content}" for source in sources
    )
    messages = [
            {
                "role": "system",
                "content": (
                    "你是电商客服回复助手。根据提供的规则依据，优化客服回复。"
                    "不得承诺规则之外的赔付、退款或时效；不得改变系统已经决定的处置结果；"
                    "只输出面向客户的一段简洁中文回复，不要Markdown。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"客户问题：{customer_content}\n\n"
                    f"系统已确定的处置结果：{draft_reply}\n\n"
                    f"规则依据：\n{policy_context}"
                ),
            },
        ]
    try:
        reply = provider.chat(messages, temperature=0.2, max_tokens=240).content
        return reply, f"{provider.name}_rag"
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        logger.warning("DeepSeek RAG reply failed; using template fallback")
        return draft_reply, "template"


def _fallback_refund_review_analysis(
    customer_content: str, sources: list[KnowledgeSource]
) -> dict[str, Any]:
    if any(keyword in customer_content for keyword in ("假货", "仿品")):
        issue_type = "counterfeit"
    elif any(keyword in customer_content for keyword in ("颜色", "型号", "规格", "不一样", "错发", "漏发")):
        issue_type = "wrong_item"
    elif any(keyword in customer_content for keyword in ("损坏", "破损", "坏了")):
        issue_type = "damage"
    elif "质量" in customer_content:
        issue_type = "quality_defect"
    else:
        issue_type = "refund_request"

    has_media = any(keyword in customer_content for keyword in ("照片", "图片", "视频"))
    missing_evidence = [item for item in REFUND_EVIDENCE if not has_media or item != "商品问题照片或视频"]
    return {
        "issue_type": issue_type,
        "evidence_completeness": "partial" if has_media else "missing",
        "missing_evidence": missing_evidence,
        "policy_condition_coverage": "medium" if sources else "low",
        "recommended_next_step": "request_evidence",
        "summary": "已提取退款争议要点；该分析仅供主管复核，不构成退款决定。",
        "analysis_source": "template",
    }


def analyse_refund_review(
    customer_content: str,
    order_context: dict[str, Any],
    sources: list[KnowledgeSource],
) -> dict[str, Any]:
    """Produce a structured, non-binding review package for a supervisor."""
    fallback = _fallback_refund_review_analysis(customer_content, sources)
    provider = get_provider("refund_analyst")
    if not provider:
        return fallback
    policy_context = "\n\n".join(
        f"【{source.title} {source.version}】\n{source.content}" for source in sources
    ) or "本轮未检索到售后规则证据。"
    messages = [
        {
            "role": "system",
            "content": (
                "你是电商退款争议的主管复核助手。只根据提供的客户诉求、订单事实和规则证据，"
                "输出一个 JSON 对象，不要 Markdown。你不能批准或拒绝退款，不能建议退款金额，"
                "不能绕过主管；只整理证据和建议下一步。"
                "字段必须为：issue_type（quality_defect/wrong_item/counterfeit/damage/refund_request/other）、"
                "evidence_completeness（complete/partial/missing）、missing_evidence（字符串数组）、"
                "policy_condition_coverage（high/medium/low）、recommended_next_step（request_evidence/supervisor_review）、"
                "summary（不超过120字）。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"客户诉求：{customer_content}\n\n"
                f"订单事实：{json.dumps(order_context, ensure_ascii=False)}\n\n"
                f"规则证据：\n{policy_context}"
            ),
        },
    ]
    try:
        raw_content = provider.chat(messages, json_mode=True, temperature=0, max_tokens=300).content
        analysis = RefundReviewAnalysis.model_validate(json.loads(raw_content)).model_dump()
        analysis["analysis_source"] = provider.name
        return analysis
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError, ValidationError) as exc:
        logger.warning("Refund review analysis failed; using template fallback (%s)", type(exc).__name__)
        fallback["analysis_fallback_reason"] = type(exc).__name__
        return fallback


def process_ticket(db: Session, ticket: Ticket) -> Ticket:
    from app.services.multi_agent_orchestrator import orchestrate_ticket

    return orchestrate_ticket(db, ticket)
