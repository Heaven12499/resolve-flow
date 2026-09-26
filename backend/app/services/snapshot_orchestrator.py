"""Stateless LangGraph orchestration over a Java-owned immutable case snapshot."""

from __future__ import annotations

import operator
from datetime import datetime, timezone
from time import perf_counter
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.internal_schemas import AgentExecutionStep, CaseAnalysisRequest, EvidenceReference
from app.services.knowledge_service import KnowledgeSource, retrieve_knowledge
from app.services.llm_provider import get_provider
from app.services.ticket_processor import (
    analyse_refund_review,
    classify_ticket,
    generate_grounded_reply,
)


DELIVERED_STATUSES = {"delivered", "signed", "completed"}


class SnapshotState(TypedDict, total=False):
    payload: CaseAnalysisRequest
    classification: Any
    plan: dict[str, Any]
    commerce_facts: dict[str, Any]
    knowledge: list[KnowledgeSource]
    knowledge_sources: list[dict[str, Any]]
    review_package: dict[str, Any]
    decision: dict[str, Any]
    reply_draft: str
    reply_source: str
    execution_trace: Annotated[list[dict[str, Any]], operator.add]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _step(
    state: SnapshotState,
    *,
    agent_name: str,
    provider: str,
    model: str | None,
    input_data: dict[str, Any],
    execute,
) -> tuple[Any, dict[str, Any]]:
    started_at = _now()
    started = perf_counter()
    sequence = len(state.get("execution_trace", [])) + 1
    try:
        value, output_data = execute()
        step = AgentExecutionStep(
            sequence=sequence,
            agent_name=agent_name,
            status="completed",
            provider=provider,
            model=model,
            input_data=input_data,
            output_data=output_data,
            duration_ms=max(0, round((perf_counter() - started) * 1000)),
            started_at=started_at,
            finished_at=_now(),
        ).model_dump(mode="json")
        return value, step
    except Exception as exc:
        step = AgentExecutionStep(
            sequence=sequence,
            agent_name=agent_name,
            status="failed",
            provider=provider,
            model=model,
            input_data=input_data,
            error=f"{type(exc).__name__}: {exc}"[:500],
            duration_ms=max(0, round((perf_counter() - started) * 1000)),
            started_at=started_at,
            finished_at=_now(),
        )
        raise RuntimeError(step.model_dump_json()) from exc


def _plan_for(intent: str) -> dict[str, Any]:
    if intent == "logistics_query":
        return {
            "route": "logistics_fast_path",
            "reason": "普通物流查询只读取订单与物流快照，不需要复杂调查。",
            "next_agents": ["commerce_evidence_skill", "risk_control", "reply"],
            "fanout_groups": [],
            "skipped_agents": [
                {"agent_name": "policy_retrieval_skill", "reason": "实时物流事实足以回答。"}
            ],
        }
    if intent == "delivery_delay_compensation":
        return {
            "route": "logistics_agent_investigation",
            "reason": "延迟补偿需要核验承诺时效、物流轨迹和补偿政策。",
            "next_agents": [
                "logistics_resolution_agent", "commerce_evidence_skill",
                "policy_retrieval_skill", "risk_control", "reply",
            ],
            "fanout_groups": [],
            "skipped_agents": [
                {"agent_name": "refund_investigation_agent", "reason": "当前不是退款争议。"}
            ],
        }
    if intent == "refund_risk_review":
        return {
            "route": "refund_agent_investigation",
            "reason": "退款或质量争议需要核验订单、客户材料和售后政策。",
            "next_agents": [
                "refund_investigation_agent", "commerce_evidence_skill",
                "policy_retrieval_skill", "refund_review_analyst",
                "risk_control", "reply",
            ],
            "fanout_groups": [],
            "skipped_agents": [],
        }
    return {
        "route": "human_handoff",
        "reason": "意图未覆盖，禁止自动处置并转人工核验。",
        "next_agents": ["risk_control", "reply"],
        "fanout_groups": [],
        "skipped_agents": [
            {"agent_name": "commerce_evidence_skill", "reason": "没有明确的业务核验目标。"},
            {"agent_name": "policy_retrieval_skill", "reason": "没有匹配的政策场景。"},
        ],
    }


def _commerce_facts(payload: CaseAnalysisRequest) -> dict[str, Any]:
    timeline = sorted(payload.logistics_timeline, key=lambda item: item.occurred_at)
    latest = timeline[-1] if timeline else None
    delivered = next(
        (item for item in reversed(timeline) if item.status in DELIVERED_STATUSES), None
    )
    comparison_time = _utc_naive(delivered.occurred_at) if delivered else _utc_naive(_now())
    promised_at = (
        _utc_naive(payload.order.promised_delivery_at)
        if payload.order.promised_delivery_at else None
    )
    return {
        "order_no": payload.order.order_no,
        "order_status": payload.order.status,
        "latest_logistics_event": (
            {
                "event_id": latest.event_id,
                "status": latest.status,
                "description": latest.description,
                "occurred_at": latest.occurred_at.isoformat(),
            } if latest else None
        ),
        "tracking_event_count": len(timeline),
        "message_count": len(payload.messages),
        "attachment_count": len(payload.evidence),
        "promised_delivery_at": promised_at.isoformat() if promised_at else None,
        "is_overdue": bool(promised_at and comparison_time > promised_at),
    }


def build_snapshot_workflow(db: Session | None):
    def supervisor(state: SnapshotState) -> SnapshotState:
        payload = state["payload"]
        provider = get_provider("supervisor")

        def execute():
            classification = classify_ticket(payload.ticket.content)
            plan = _plan_for(classification.intent)
            return (classification, plan), plan

        (classification, plan), trace = _step(
            state,
            agent_name="supervisor",
            provider=provider.name if provider else "rules",
            model=provider.model if provider else None,
            input_data={"title": payload.ticket.title, "content_length": len(payload.ticket.content)},
            execute=execute,
        )
        return {"classification": classification, "plan": plan, "execution_trace": [trace]}

    def route_after_supervisor(state: SnapshotState) -> str:
        return state["classification"].intent

    def specialist(state: SnapshotState, agent_name: str, goal: str) -> SnapshotState:
        payload = state["payload"]
        output = {
            "goal": goal,
            "selected_skills": ["commerce_evidence", "policy_retrieval"],
            "snapshot_version": payload.business_version,
            "business_writes_allowed": False,
        }
        _, trace = _step(
            state,
            agent_name=agent_name,
            provider="rules",
            model=None,
            input_data={"ticket_id": payload.ticket_id, "intent": state["classification"].intent},
            execute=lambda: (output, output),
        )
        return {"execution_trace": [trace]}

    def logistics_specialist(state: SnapshotState) -> SnapshotState:
        return specialist(state, "logistics_resolution_agent", "核验延迟事实并形成非约束性补偿建议")

    def refund_specialist(state: SnapshotState) -> SnapshotState:
        return specialist(state, "refund_investigation_agent", "核验退款争议事实、附件和政策证据")

    def commerce_skill(state: SnapshotState) -> SnapshotState:
        payload = state["payload"]

        def execute():
            facts = _commerce_facts(payload)
            return facts, facts

        facts, trace = _step(
            state,
            agent_name="commerce_evidence_skill",
            provider="snapshot",
            model=None,
            input_data={
                "order_no": payload.order.order_no,
                "tracking_events": len(payload.logistics_timeline),
                "messages": len(payload.messages),
                "attachments": len(payload.evidence),
            },
            execute=execute,
        )
        return {"commerce_facts": facts, "execution_trace": [trace]}

    def policy_skill(state: SnapshotState) -> SnapshotState:
        payload = state["payload"]
        category = "logistics" if state["classification"].intent == "delivery_delay_compensation" else "after_sales"

        def execute():
            sources = retrieve_knowledge(db, payload.ticket.content, category=category) if db else []
            rows = [
                {
                    "document_id": source.document_id,
                    "title": source.title,
                    "version": source.version,
                    "category": source.category,
                    "score": round(source.score, 4),
                }
                for source in sources
            ]
            return (sources, rows), {"category": category, "sources": rows}

        (sources, rows), trace = _step(
            state,
            agent_name="policy_retrieval_skill",
            provider="chroma" if db else "disabled",
            model=None,
            input_data={"category": category, "query_length": len(payload.ticket.content)},
            execute=execute,
        )
        return {"knowledge": sources, "knowledge_sources": rows, "execution_trace": [trace]}

    def refund_analyst(state: SnapshotState) -> SnapshotState:
        payload = state["payload"]
        provider = get_provider("refund_analyst")

        def execute():
            review = analyse_refund_review(
                payload.ticket.content,
                state.get("commerce_facts", {}),
                state.get("knowledge", []),
            )
            return review, review

        review, trace = _step(
            state,
            agent_name="refund_review_analyst",
            provider=provider.name if provider else "template",
            model=provider.model if provider else None,
            input_data={
                "attachment_count": len(payload.evidence),
                "policy_source_count": len(state.get("knowledge", [])),
            },
            execute=execute,
        )
        return {"review_package": review, "execution_trace": [trace]}

    def risk_control(state: SnapshotState) -> SnapshotState:
        intent = state["classification"].intent
        facts = state.get("commerce_facts", {})
        if intent == "logistics_query" and facts.get("latest_logistics_event"):
            decision = {"recommended_action": "QUERY_LOGISTICS", "requires_human_approval": False}
        elif intent == "delivery_delay_compensation" and facts.get("is_overdue") and facts.get("latest_logistics_event"):
            decision = {
                "recommended_action": "REQUEST_COUPON_APPROVAL",
                "requires_human_approval": True,
                "suggested_coupon_amount": 5,
            }
        elif intent == "refund_risk_review":
            decision = {"recommended_action": "ESCALATE_REFUND_REVIEW", "requires_human_approval": True}
        else:
            decision = {"recommended_action": "ESCALATE_TO_HUMAN", "requires_human_approval": True}
        _, trace = _step(
            state,
            agent_name="risk_control",
            provider="rules",
            model=None,
            input_data={"intent": intent, "business_writes_allowed": False},
            execute=lambda: (decision, decision),
        )
        return {"decision": decision, "execution_trace": [trace]}

    def reply(state: SnapshotState) -> SnapshotState:
        payload = state["payload"]
        action = state["decision"]["recommended_action"]
        facts = state.get("commerce_facts", {})
        if action == "QUERY_LOGISTICS":
            latest = facts["latest_logistics_event"]
            draft = f"您好，订单 {payload.order.order_no} 当前物流状态：{latest['description']}。我们会继续关注配送进度。"
        elif action == "REQUEST_COUPON_APPROVAL":
            draft = "经核实物流已超过承诺时效，系统建议发放5元优惠券，需由客服审批后生效。"
        elif action == "ESCALATE_REFUND_REVIEW":
            draft = "该诉求涉及退款或质量争议，已建议转交主管复核，AI不会直接执行退款。"
        else:
            draft = "当前信息不足以自动处置，建议转交人工客服进一步核验。"

        def execute():
            final_reply, source = generate_grounded_reply(
                payload.ticket.content, draft, state.get("knowledge", [])
            )
            return (final_reply, source), {"reply_draft": final_reply, "source": source}

        provider = get_provider("reply")
        (final_reply, source), trace = _step(
            state,
            agent_name="reply",
            provider=provider.name if provider and state.get("knowledge") else "template",
            model=provider.model if provider and state.get("knowledge") else None,
            input_data={"recommended_action": action, "policy_source_count": len(state.get("knowledge", []))},
            execute=execute,
        )
        return {"reply_draft": final_reply, "reply_source": source, "execution_trace": [trace]}

    graph = StateGraph(SnapshotState)
    graph.add_node("supervisor", supervisor)
    graph.add_node("logistics_resolution_agent", logistics_specialist)
    graph.add_node("refund_investigation_agent", refund_specialist)
    graph.add_node("commerce_evidence_skill", commerce_skill)
    graph.add_node("policy_retrieval_skill", policy_skill)
    graph.add_node("refund_review_analyst", refund_analyst)
    graph.add_node("risk_control", risk_control)
    graph.add_node("reply", reply)
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {
            "logistics_query": "commerce_evidence_skill",
            "delivery_delay_compensation": "logistics_resolution_agent",
            "refund_risk_review": "refund_investigation_agent",
            "other": "risk_control",
        },
    )
    graph.add_edge("logistics_resolution_agent", "commerce_evidence_skill")
    graph.add_edge("refund_investigation_agent", "commerce_evidence_skill")

    def route_after_commerce(state: SnapshotState) -> str:
        return "risk_control" if state["classification"].intent == "logistics_query" else "policy_retrieval_skill"

    graph.add_conditional_edges(
        "commerce_evidence_skill", route_after_commerce,
        {"risk_control": "risk_control", "policy_retrieval_skill": "policy_retrieval_skill"},
    )

    def route_after_policy(state: SnapshotState) -> str:
        return "refund_review_analyst" if state["classification"].intent == "refund_risk_review" else "risk_control"

    graph.add_conditional_edges(
        "policy_retrieval_skill", route_after_policy,
        {"refund_review_analyst": "refund_review_analyst", "risk_control": "risk_control"},
    )
    graph.add_edge("refund_review_analyst", "risk_control")
    graph.add_edge("risk_control", "reply")
    graph.add_edge("reply", END)
    return graph.compile()


def orchestrate_snapshot(payload: CaseAnalysisRequest, db: Session | None = None) -> SnapshotState:
    return build_snapshot_workflow(db).invoke({"payload": payload, "execution_trace": []})


def evidence_references(payload: CaseAnalysisRequest, sources: list[dict[str, Any]]) -> list[EvidenceReference]:
    references = [
        EvidenceReference(type="tracking", reference=f"tracking:{item.event_id or index + 1}")
        for index, item in enumerate(payload.logistics_timeline)
    ]
    references.extend(
        EvidenceReference(type="attachment", reference=f"evidence:{item.evidence_id or index + 1}")
        for index, item in enumerate(payload.evidence)
    )
    references.extend(
        EvidenceReference(type="policy", reference=f"policy:{item['document_id']}")
        for item in sources
    )
    return references
