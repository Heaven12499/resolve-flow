"""Stateless LangGraph orchestration over a Java-owned immutable case snapshot."""

from __future__ import annotations

import operator
from datetime import datetime, timezone
from time import perf_counter
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.core.config import settings
from app.internal_schemas import AgentExecutionStep, CaseAnalysisRequest, EvidenceReference
from app.services.case_investigation import (
    EvidenceGateResult,
    MAX_CASE_STEPS,
    choose_case_action,
    evaluate_evidence,
)
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
    specialist_agent: str
    investigation_scenario: str
    case_step: int
    case_history: list[dict[str, Any]]
    case_decision: dict[str, Any]
    evidence_gate: dict[str, Any]
    pending_question: str | None
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
    overdue = bool(promised_at and comparison_time > promised_at)
    anomaly_type = None
    if latest:
        if delivered and overdue:
            anomaly_type = "delivered_late"
        elif overdue:
            anomaly_type = "in_transit_overdue"
        else:
            anomaly_type = "none"
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
        "is_overdue": overdue,
        "anomaly_type": anomaly_type,
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
        update: SnapshotState = {
            "classification": classification,
            "plan": plan,
            "execution_trace": [trace],
        }
        if classification.intent in {"delivery_delay_compensation", "refund_risk_review"}:
            scenario = "delivery_delay" if classification.intent == "delivery_delay_compensation" else "refund"
            customer_message_count = sum(
                1 for message in payload.messages if message.sender_type == "customer"
            )
            update.update(
                specialist_agent=(
                    "logistics_resolution_agent"
                    if scenario == "delivery_delay" else "refund_investigation_agent"
                ),
                investigation_scenario=scenario,
                case_step=0,
                case_history=[],
                pending_question=None,
                evidence_gate=evaluate_evidence(
                    [],
                    ticket_content=payload.ticket.content,
                    source_count=0,
                    retrieval_required=settings.rag_enabled,
                    customer_message_count=customer_message_count,
                    pending_question=None,
                    step=0,
                    scenario=scenario,
                ).model_dump(),
            )
        return update

    def route_after_supervisor(state: SnapshotState) -> str:
        return state["classification"].intent

    def specialist(state: SnapshotState) -> SnapshotState:
        payload = state["payload"]
        scenario = state["investigation_scenario"]
        agent_name = state["specialist_agent"]
        provider_key = "logistics_resolution" if scenario == "delivery_delay" else "refund_investigation"
        provider = get_provider(provider_key) or get_provider("case_manager")
        gate = EvidenceGateResult.model_validate(state["evidence_gate"])

        def execute():
            decision, source, fallback_reason = choose_case_action(
                payload.ticket.content,
                state["case_history"],
                gate,
                step=state["case_step"],
                scenario=scenario,
            )
            output = {
                **decision.model_dump(),
                "decision_source": source,
                "step": state["case_step"] + 1,
                "max_steps": MAX_CASE_STEPS,
                "business_writes_allowed": False,
            }
            if fallback_reason:
                output["fallback_reason"] = fallback_reason
            return output, output

        decision, trace = _step(
            state,
            agent_name=agent_name,
            provider=provider.name if provider else "rules",
            model=provider.model if provider else None,
            input_data={
                "goal": (
                    "准备延迟补偿事实包" if scenario == "delivery_delay"
                    else "准备退款争议复核事实包"
                ),
                "step": state["case_step"] + 1,
                "evidence_gate": state["evidence_gate"],
                "observations": [
                    {
                        "action": item.get("action"),
                        "ok": item.get("ok"),
                        "summary": item.get("summary"),
                        "query": item.get("query"),
                    }
                    for item in state["case_history"]
                ],
                "allowed_skills": ["commerce_evidence", "policy_retrieval"],
                "allowed_actions": ["ask_customer", "finish"],
            },
            execute=execute,
        )
        return {
            "case_decision": decision,
            "case_step": state["case_step"] + 1,
            "execution_trace": [trace],
        }

    def after_specialist(state: SnapshotState) -> str:
        return "evidence_gate" if state["case_decision"]["action"] == "finish" else "case_action"

    def case_action(state: SnapshotState) -> SnapshotState:
        payload = state["payload"]
        decision = state["case_decision"]
        action = decision["action"]
        arguments = decision.get("arguments") or {}
        history = list(state["case_history"])
        category = "logistics" if state["investigation_scenario"] == "delivery_delay" else "after_sales"
        update: SnapshotState = {}

        def execute_action():
            if action == "get_order":
                data = {
                    "order_found": True,
                    "order_no": payload.order.order_no,
                    "product_name": payload.order.product_name,
                    "amount": str(payload.order.amount),
                    "status": payload.order.status,
                }
                observation = {"action": action, "ok": True, "summary": "已核验订单快照", "data": data}
            elif action == "analyze_delivery_timeline":
                data = _commerce_facts(payload)
                observation = {
                    "action": action,
                    "ok": bool(data["latest_logistics_event"]),
                    "summary": "已重建物流时间线并计算承诺时效",
                    "data": data,
                }
            elif action == "get_ticket_messages":
                customer_messages = [
                    message for message in payload.messages if message.sender_type == "customer"
                ]
                data = {
                    "customer_message_count": len(customer_messages),
                    "messages": [
                        {"sender_type": message.sender_type, "content": message.content[:500]}
                        for message in payload.messages
                    ],
                }
                observation = {"action": action, "ok": True, "summary": "已读取完整工单对话快照", "data": data}
            elif action == "inspect_customer_evidence":
                customer_message_count = sum(
                    1 for message in payload.messages if message.sender_type == "customer"
                )
                data = {
                    "customer_message_count": customer_message_count,
                    "evidence_present": bool(payload.evidence),
                    "attachments": [
                        {
                            "evidence_id": item.evidence_id,
                            "file_name": item.file_name,
                            "media_type": item.media_type,
                        }
                        for item in payload.evidence
                    ],
                }
                observation = {"action": action, "ok": True, "summary": "已核验结构化客户附件", "data": data}
            elif action == "search_policy":
                query = str(arguments.get("query") or payload.ticket.content)
                sources = retrieve_knowledge(db, query, category=category) if db else []
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
                observation = {
                    "action": action,
                    "ok": bool(rows) or not settings.rag_enabled,
                    "summary": f"已检索到 {len(rows)} 条政策证据",
                    "query": query,
                    "data": {"sources": rows},
                }
                merged_sources = {
                    source.chunk_id: source for source in [*state.get("knowledge", []), *sources]
                }
                ranked_sources = sorted(
                    merged_sources.values(), key=lambda source: source.score, reverse=True
                )[:3]
                update["knowledge"] = ranked_sources
                update["knowledge_sources"] = [
                    {
                        "document_id": source.document_id,
                        "title": source.title,
                        "version": source.version,
                        "category": source.category,
                        "score": round(source.score, 4),
                    }
                    for source in ranked_sources
                ]
            elif action == "ask_customer":
                question = decision.get("question") or "请补充完成退款复核所需的材料。"
                observation = {
                    "action": action,
                    "ok": True,
                    "summary": "已生成客户补充材料请求",
                    "data": {"question": question},
                }
                update["pending_question"] = question
            else:
                raise ValueError(f"unsupported specialist action: {action}")
            return observation, observation

        skill_name = (
            "case_action_ask_customer" if action == "ask_customer"
            else "policy_retrieval_skill" if action == "search_policy"
            else "commerce_evidence_skill"
        )
        observation, trace = _step(
            state,
            agent_name=skill_name,
            provider="workflow" if action == "ask_customer" else "chroma" if action == "search_policy" else "snapshot",
            model=None,
            input_data={
                "operation": action,
                "arguments": arguments,
                "read_only": action != "ask_customer",
                "requested_by": state["specialist_agent"],
            },
            execute=execute_action,
        )
        history.append(observation)
        update["case_history"] = history
        if action in {
            "get_order", "analyze_delivery_timeline", "get_ticket_messages",
            "inspect_customer_evidence",
        }:
            update["commerce_facts"] = {**state.get("commerce_facts", {}), **observation["data"]}
        update["execution_trace"] = [trace]
        return update

    def evidence_gate(state: SnapshotState) -> SnapshotState:
        payload = state["payload"]
        customer_message_count = sum(
            1 for message in payload.messages if message.sender_type == "customer"
        )

        def execute():
            gate = evaluate_evidence(
                state["case_history"],
                ticket_content=payload.ticket.content,
                source_count=len(state.get("knowledge_sources", [])),
                retrieval_required=settings.rag_enabled,
                customer_message_count=customer_message_count,
                pending_question=state.get("pending_question"),
                step=state["case_step"],
                scenario=state["investigation_scenario"],
            ).model_dump()
            return gate, gate

        gate, trace = _step(
            state,
            agent_name="evidence_gate",
            provider="rules",
            model=None,
            input_data={
                "step": state["case_step"],
                "customer_message_count": customer_message_count,
                "pending_question": state.get("pending_question"),
            },
            execute=execute,
        )
        return {"evidence_gate": gate, "execution_trace": [trace]}

    def after_evidence_gate(state: SnapshotState) -> str:
        disposition = state["evidence_gate"]["disposition"]
        if disposition == "waiting_customer":
            return "risk_control"
        if disposition in {"ready", "budget_exhausted"}:
            return "refund_review_analyst" if state["investigation_scenario"] == "refund" else "risk_control"
        return state["specialist_agent"]

    def fast_commerce_skill(state: SnapshotState) -> SnapshotState:
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
                "operation": "analyze_delivery_timeline",
                "order_no": payload.order.order_no,
                "tracking_events": len(payload.logistics_timeline),
                "read_only": True,
            },
            execute=execute,
        )
        return {"commerce_facts": facts, "execution_trace": [trace]}

    def refund_analyst(state: SnapshotState) -> SnapshotState:
        payload = state["payload"]
        provider = get_provider("refund_analyst")

        def execute():
            review = analyse_refund_review(
                payload.ticket.content,
                state.get("commerce_facts", {}),
                state.get("knowledge", []),
            )
            review["case_history"] = state.get("case_history", [])
            review["evidence_gate"] = state.get("evidence_gate", {})
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
        gate_disposition = state.get("evidence_gate", {}).get("disposition")
        if state.get("pending_question"):
            decision = {
                "recommended_action": "REQUEST_CUSTOMER_EVIDENCE",
                "requires_human_approval": False,
                "pending_question": state["pending_question"],
            }
        elif intent == "logistics_query" and facts.get("latest_logistics_event"):
            decision = {"recommended_action": "QUERY_LOGISTICS", "requires_human_approval": False}
        elif (
            intent == "delivery_delay_compensation"
            and gate_disposition == "ready"
            and facts.get("is_overdue")
            and facts.get("latest_logistics_event")
        ):
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
            input_data={
                "intent": intent,
                "evidence_gate": state.get("evidence_gate"),
                "business_writes_allowed": False,
            },
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
        elif action == "REQUEST_CUSTOMER_EVIDENCE":
            draft = state.get("pending_question") or "为继续处理，请补充相关证明材料。"
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
    graph.add_node("logistics_resolution_agent", specialist)
    graph.add_node("refund_investigation_agent", specialist)
    graph.add_node("case_action", case_action)
    graph.add_node("evidence_gate", evidence_gate)
    graph.add_node("fast_commerce_evidence_skill", fast_commerce_skill)
    graph.add_node("refund_review_analyst", refund_analyst)
    graph.add_node("risk_control", risk_control)
    graph.add_node("reply", reply)
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {
            "logistics_query": "fast_commerce_evidence_skill",
            "delivery_delay_compensation": "logistics_resolution_agent",
            "refund_risk_review": "refund_investigation_agent",
            "other": "risk_control",
        },
    )
    graph.add_conditional_edges(
        "logistics_resolution_agent",
        after_specialist,
        {"case_action": "case_action", "evidence_gate": "evidence_gate"},
    )
    graph.add_conditional_edges(
        "refund_investigation_agent",
        after_specialist,
        {"case_action": "case_action", "evidence_gate": "evidence_gate"},
    )
    graph.add_edge("case_action", "evidence_gate")
    graph.add_conditional_edges(
        "evidence_gate",
        after_evidence_gate,
        {
            "logistics_resolution_agent": "logistics_resolution_agent",
            "refund_investigation_agent": "refund_investigation_agent",
            "refund_review_analyst": "refund_review_analyst",
            "risk_control": "risk_control",
        },
    )
    graph.add_edge("fast_commerce_evidence_skill", "risk_control")
    graph.add_edge("refund_review_analyst", "risk_control")
    graph.add_edge("risk_control", "reply")
    graph.add_edge("reply", END)
    return graph.compile()


def orchestrate_snapshot(payload: CaseAnalysisRequest, db: Session | None = None) -> SnapshotState:
    return build_snapshot_workflow(db).invoke(
        {"payload": payload, "execution_trace": []},
        config={"recursion_limit": 64},
    )


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
