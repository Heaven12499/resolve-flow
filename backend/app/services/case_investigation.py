"""Planning and deterministic evidence gates for specialist Agents."""

import json
import logging
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.services.llm_provider import get_provider


logger = logging.getLogger(__name__)

MAX_CASE_STEPS = 10
MAX_POLICY_SEARCHES = 3
InvestigationScenario = Literal["refund", "delivery_delay"]

CaseAction = Literal[
    "get_order",
    "get_logistics",
    "search_policy",
    "get_ticket_messages",
    "list_customer_evidence",
    "ask_customer",
    "finish",
]


class CaseManagerDecision(BaseModel):
    action: CaseAction
    reason: str = Field(min_length=1, max_length=300)
    arguments: dict[str, Any] = Field(default_factory=dict)
    question: str | None = Field(default=None, min_length=2, max_length=500)


class EvidenceGateResult(BaseModel):
    accepted: bool
    disposition: Literal["continue", "waiting_customer", "ready", "budget_exhausted"]
    checks: dict[str, bool]
    missing_slots: list[str]
    reason: str


def _history_actions(history: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("action")) for item in history]


def _latest(history: list[dict[str, Any]], action: str) -> dict[str, Any] | None:
    return next((item for item in reversed(history) if item.get("action") == action), None)


def evaluate_evidence(
    history: list[dict[str, Any]],
    *,
    ticket_content: str,
    source_count: int,
    retrieval_required: bool,
    customer_message_count: int,
    pending_question: str | None,
    step: int,
    scenario: InvestigationScenario = "refund",
) -> EvidenceGateResult:
    """Check evidence completeness without prescribing the Agent's next tool."""
    order = _latest(history, "get_order")
    logistics = _latest(history, "get_logistics")
    policy = _latest(history, "search_policy")
    messages = _latest(history, "get_ticket_messages")
    evidence = _latest(history, "list_customer_evidence")
    needs_logistics = scenario == "delivery_delay" or any(
        keyword in ticket_content for keyword in ("物流", "快递", "配送", "延迟", "晚到")
    )

    message_snapshot = int((messages or {}).get("data", {}).get("customer_message_count", -1))
    evidence_snapshot = int((evidence or {}).get("data", {}).get("customer_message_count", -1))
    evidence_present = bool((evidence or {}).get("data", {}).get("evidence_present"))
    checks: dict[str, bool] = {
        "order_verified": bool(order and order.get("ok")),
        "conversation_reviewed": message_snapshot == customer_message_count,
        "policy_grounded": bool(policy) and (source_count > 0 or not retrieval_required),
        "logistics_checked_when_relevant": not needs_logistics or bool(logistics),
    }
    if scenario == "refund":
        checks.update(
            evidence_status_known=evidence_snapshot == customer_message_count,
            customer_evidence_present=evidence_present,
        )
    missing = [name for name, passed in checks.items() if not passed]
    if pending_question:
        return EvidenceGateResult(
            accepted=False,
            disposition="waiting_customer",
            checks=checks,
            missing_slots=missing,
            reason="Agent 已向客户请求补充材料，任务持久化暂停。",
        )
    if retrieval_required and source_count == 0 and _history_actions(history).count("search_policy") >= MAX_POLICY_SEARCHES:
        return EvidenceGateResult(
            accepted=False,
            disposition="budget_exhausted",
            checks=checks,
            missing_slots=missing,
            reason="规则检索已达到安全上限，携带无可靠规则证据的状态转人工复核。",
        )
    if not missing:
        return EvidenceGateResult(
            accepted=True,
            disposition="ready",
            checks=checks,
            missing_slots=[],
            reason=(
                "退款复核所需的订单、对话、规则与客户材料均已核验。"
                if scenario == "refund"
                else "延迟补偿所需的订单、物流、对话与政策证据均已核验。"
            ),
        )
    if step >= MAX_CASE_STEPS:
        return EvidenceGateResult(
            accepted=False,
            disposition="budget_exhausted",
            checks=checks,
            missing_slots=missing,
            reason="调查预算已耗尽，携带现有证据转人工复核。",
        )
    return EvidenceGateResult(
        accepted=False,
        disposition="continue",
        checks=checks,
        missing_slots=missing,
        reason="证据尚不完整，由当前 Specialist Agent 自主选择下一步调查动作。",
    )


def _fallback_decision(
    ticket_content: str,
    history: list[dict[str, Any]],
    gate: EvidenceGateResult,
    scenario: InvestigationScenario,
) -> CaseManagerDecision:
    """Offline baseline; production models may choose another safe tool."""
    missing = set(gate.missing_slots)
    actions = _history_actions(history)
    if "order_verified" in missing:
        return CaseManagerDecision(action="get_order", reason="核验客户诉求关联的订单事实。")
    if "conversation_reviewed" in missing:
        return CaseManagerDecision(action="get_ticket_messages", reason="读取完整对话，避免遗漏或重复提问。")
    if "logistics_checked_when_relevant" in missing:
        return CaseManagerDecision(action="get_logistics", reason="客户同时提到物流问题，需要补充物流事实。")
    if "policy_grounded" in missing:
        search_count = actions.count("search_policy")
        suffixes = (
            ("售后退款适用条件", "商品质量缺陷 证据要求 主管复核", "退款争议 例外条款 人工审核")
            if scenario == "refund"
            else ("物流延迟补偿条件", "物流停滞 补偿例外", "延迟发货 优惠券审批边界")
        )
        suffix = suffixes[min(search_count, len(suffixes) - 1)]
        return CaseManagerDecision(
            action="search_policy",
            reason="检索能够支撑处置结论的业务规则。",
            arguments={"query": f"{ticket_content} {suffix}"},
        )
    if "evidence_status_known" in missing:
        return CaseManagerDecision(action="list_customer_evidence", reason="检查客户是否已经补充图片、视频或检测材料。")
    if "customer_evidence_present" in missing:
        return CaseManagerDecision(
            action="ask_customer",
            reason="退款复核缺少能够证明商品问题的客户材料。",
            question="为继续退款复核，请补充商品问题的照片、视频或检测说明。",
        )
    return CaseManagerDecision(action="finish", reason="当前调查目标已经完成。")


def choose_case_action(
    ticket_content: str,
    history: list[dict[str, Any]],
    gate: EvidenceGateResult,
    *,
    step: int,
    scenario: InvestigationScenario = "refund",
) -> tuple[CaseManagerDecision, str, str | None]:
    """Choose one action; guards constrain capability and budget, not tool order."""
    fallback = _fallback_decision(ticket_content, history, gate, scenario)
    if gate.disposition in {"ready", "budget_exhausted"} or step >= MAX_CASE_STEPS:
        return CaseManagerDecision(action="finish", reason=gate.reason), "rules", None
    agent_name = "refund_investigation" if scenario == "refund" else "logistics_resolution"
    provider = get_provider(agent_name) or get_provider("case_manager")
    if not provider:
        return fallback, "rules", None

    compact_history = [
        {"action": item.get("action"), "ok": item.get("ok"), "summary": item.get("summary"), "query": item.get("query")}
        for item in history
    ]
    messages = [
        {
            "role": "system",
            "content": (
                f"你是电商售后 {agent_name} Agent，目标是收集足够的"
                f"{'退款复核' if scenario == 'refund' else '延迟补偿'}证据。"
                "可自主选择 get_order、get_logistics、search_policy、get_ticket_messages、"
                "list_customer_evidence、ask_customer、finish。"
                "这些能力均为只读或客户沟通能力；不得退款、赔付、审批、修改订单或绕过人工。"
                "每轮只选择一个动作，以 JSON 返回 action、reason、arguments、question。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"目标：准备可供规则引擎和人工复核的{'退款争议' if scenario == 'refund' else '延迟补偿'}事实包\n"
                f"客户诉求：{ticket_content}\n"
                f"步骤：{step}/{MAX_CASE_STEPS}\n"
                f"Evidence Gate 缺失项：{json.dumps(gate.missing_slots, ensure_ascii=False)}\n"
                f"观察历史：{json.dumps(compact_history, ensure_ascii=False)}"
            ),
        },
    ]
    try:
        raw = provider.chat(messages, json_mode=True, temperature=0, max_tokens=240).content
        decision = CaseManagerDecision.model_validate(json.loads(raw))
        if decision.action == "search_policy":
            if _history_actions(history).count("search_policy") >= MAX_POLICY_SEARCHES:
                return fallback, "rules", "policy_search_limit"
            query = str(decision.arguments.get("query", "")).strip()
            if not query:
                decision.arguments["query"] = ticket_content
        if decision.action == "ask_customer" and not decision.question:
            decision.question = fallback.question or "请补充完成退款复核所需的材料。"
        return decision, provider.name, None
    except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError, ValidationError) as exc:
        logger.warning("Specialist Agent planning failed; using safe baseline (%s)", type(exc).__name__)
        return fallback, "rules", f"{provider.name}_{type(exc).__name__}"
