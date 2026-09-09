"""Observable Supervisor-Specialist workflow orchestration.

The Supervisor delegates complex cases to bounded Logistics Resolution and
Refund Investigation Agents.  Both specialists share two deterministic Skills;
risk and action authority remains in the Rule Engine.
"""

from dataclasses import asdict
from time import perf_counter
from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AgentRun, ApprovalTask, AuditLog, CaseAgentState, Ticket, TicketMessage, utc_now
from app.services.case_investigation import EvidenceGateResult, choose_case_action, evaluate_evidence
from app.services.agent_skills import (
    SKILL_CATALOG,
    execute_agent_skill,
    execute_commerce_evidence_skill,
    skill_for_action,
)
from app.services.case_tools import READ_ONLY_CASE_TOOLS
from app.services.knowledge_service import KnowledgeSource
from app.services.llm_provider import get_provider
from app.services.ticket_processor import (
    ClassificationResult,
    analyse_refund_review,
    classify_ticket,
    generate_grounded_reply,
)


def _compact(value: Any) -> Any:
    """Keep observability useful without persisting large prompts repeatedly."""
    if isinstance(value, str):
        return value[:500]
    if isinstance(value, dict):
        return {key: _compact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_compact(item) for item in value]
    return value


def _trace(
    db: Session,
    *,
    ticket: Ticket,
    sequence: int,
    agent_name: str,
    provider: str,
    model: str | None,
    input_data: dict[str, Any],
    execute: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    started_at = utc_now()
    started = perf_counter()
    run = AgentRun(
        ticket_id=ticket.id,
        sequence=sequence,
        agent_name=agent_name,
        status="running",
        provider=provider,
        model=model,
        input_data=_compact(input_data),
        started_at=started_at,
    )
    db.add(run)
    db.flush()
    try:
        output = execute()
    except Exception as exc:
        run.status = "failed"
        run.error = type(exc).__name__
        run.duration_ms = round((perf_counter() - started) * 1000)
        run.finished_at = utc_now()
        raise
    run.status = "completed"
    run.output_data = _compact(output)
    run.duration_ms = round((perf_counter() - started) * 1000)
    run.finished_at = utc_now()
    return output


def _sources_from_payload(rows: list[dict[str, Any]]) -> list[KnowledgeSource]:
    """Rehydrate typed sources at the boundary of model-facing functions."""
    return [KnowledgeSource(**row) for row in rows]


def _execution_plan(classification: ClassificationResult) -> dict[str, Any]:
    """Let the Supervisor select a minimal, safe workflow for each intent.

    The plan is deterministic because routing and risk authority must remain in
    backend code.  An LLM may classify the request, but it may not decide which
    safety gate can be bypassed.
    """
    if classification.intent == "logistics_query":
        return {
            "route": "logistics_fast_path",
            "reason": "仅需核验订单实时物流，不涉及权益或售后政策判断。",
            "next_agents": ["commerce_evidence_skill", "risk_control", "reply"],
            "delegated_agent": None,
            "fanout_groups": [],
            "skipped_agents": [
                {"agent_name": "policy_retrieval_skill", "reason": "订单物流系统已提供实时事实，无需检索政策库。"},
            ],
        }
    if classification.intent == "delivery_delay_compensation":
        return {
            "route": "logistics_agent_investigation",
            "reason": "延迟补偿存在多步证据依赖，委派 Logistics Resolution Agent 自主调查。",
            "next_agents": ["logistics_resolution_agent", "evidence_gate", "risk_control", "reply"],
            "delegated_agent": "logistics_resolution_agent",
            "fanout_groups": [],
            "agent_loop": {
                "agent": "logistics_resolution_agent",
                "skills": SKILL_CATALOG,
                "max_steps": 10,
            },
            "skipped_agents": [{"agent_name": "refund_investigation_agent", "reason": "当前为物流延迟补偿场景。"}],
        }
    if classification.intent == "refund_risk_review":
        return {
            "route": "refund_agent_investigation",
            "reason": "退款属于高风险事项，委派 Refund Investigation Agent 自主调查、补齐证据或向客户追问。",
            "next_agents": ["refund_investigation_agent", "evidence_gate", "refund_review_analyst", "risk_control", "reply"],
            "delegated_agent": "refund_investigation_agent",
            "fanout_groups": [],
            "agent_loop": {
                "agent": "refund_investigation_agent",
                "skills": SKILL_CATALOG,
                "allowed_tools": sorted(READ_ONLY_CASE_TOOLS),
                "allowed_actions": ["ask_customer", "finish"],
                "max_steps": 10,
            },
            "skipped_agents": [],
        }
    return {
        "route": "human_handoff",
        "reason": "意图置信不足或不在自动处置范围，直接进入人工兜底。",
        "next_agents": ["risk_control", "reply"],
        "delegated_agent": None,
        "fanout_groups": [],
        "skipped_agents": [
            {"agent_name": "commerce_evidence_skill", "reason": "当前问题不需要订单或物流核验。"},
            {"agent_name": "policy_retrieval_skill", "reason": "当前问题没有匹配的自动处置政策。"},
        ],
    }


def _risk_decision(
    classification: ClassificationResult,
    order_context: dict[str, Any],
    knowledge_context: dict[str, Any],
) -> dict[str, Any]:
    action = classification.suggested_action
    if action == "request_coupon_approval":
        # When policy retrieval is enabled, a compensation proposal must be
        # grounded in evidence from this execution.  A model classification alone
        # is never sufficient to create a money-related approval request.
        if knowledge_context["retrieval_required"] and not knowledge_context["source_count"]:
            return {
                "action": "escalate_to_human",
                "status": "escalated",
                "requires_human_approval": True,
                "reason": "补偿规则证据不可用，禁止生成自动补偿建议，转人工处理。",
            }
        if not order_context["latest_logistics_event"]:
            return {
                "action": "escalate_to_human",
                "status": "escalated",
                "requires_human_approval": True,
                "reason": "缺少订单物流事实，禁止生成自动补偿建议，转人工处理。",
            }
        if order_context.get("conflicts"):
            return {
                "action": "escalate_to_human",
                "status": "escalated",
                "requires_human_approval": True,
                "reason": "订单状态与物流轨迹冲突，禁止生成自动补偿建议，转人工核验。",
            }
        if order_context.get("is_overdue") is not True:
            return {
                "action": "escalate_to_human",
                "status": "escalated",
                "requires_human_approval": True,
                "reason": "物流时序未确认超过承诺时效，禁止生成自动补偿建议。",
            }
        return {
            "action": action,
            "status": "pending_approval",
            "requires_human_approval": True,
            "reason": "补偿属于资金权益操作，必须由人工确认。",
        }
    if action == "escalate_to_supervisor":
        return {
            "action": action,
            "status": "escalated",
            "requires_human_approval": True,
            "reason": "退款和质量争议属于高风险操作，禁止 AI 自动执行。",
        }
    if action == "query_logistics" and order_context["latest_logistics_event"]:
        return {
            "action": action,
            "status": "resolved",
            "requires_human_approval": False,
            "reason": "仅查询订单物流信息，无资金或退款风险。",
        }
    return {
        "action": "escalate_to_human",
        "status": "escalated",
        "requires_human_approval": True,
        "reason": "缺少可自动处置依据，转人工处理。",
    }


def _draft_reply(
    decision: dict[str, Any], order_context: dict[str, Any], review_package: dict[str, Any] | None = None
) -> tuple[str, dict[str, Any]]:
    action = decision["action"]
    if action == "request_coupon_approval":
        coupon_amount = 5
        proposal = {
            "coupon_amount": coupon_amount,
            "currency": "CNY",
            "reason": "物流延迟补偿",
            "approval_level": "agent" if coupon_amount <= settings.agent_coupon_approval_limit else "supervisor",
        }
        return "因物流延迟，系统建议发放5元优惠券补偿，已提交客服审批。", proposal
    if action == "escalate_to_supervisor":
        proposal = {
            "reason": "涉及退款或质量争议，禁止AI直接执行退款",
            "required_evidence": (review_package or {}).get(
                "missing_evidence", ["订单信息", "商品问题照片或视频", "签收及使用情况"]
            ),
        }
        if review_package:
            proposal["review_package"] = review_package
        return "该退款诉求已标记为高风险，工单已转交主管复核，请补充商品问题的照片或视频。", proposal
    if action == "query_logistics":
        return (
            f"您好，订单 {order_context['order_no']} 当前物流状态："
            f"{order_context['latest_logistics_event']}。我们会继续关注配送进度。",
            {
                "order_no": order_context["order_no"],
                "logistics_status": order_context["latest_logistics_status"],
                "latest_event": order_context["latest_logistics_event"],
            },
        )
    return "该问题需要人工进一步判断，工单已转交人工客服处理。", {"reason": "unsupported_intent"}


class TicketWorkflowState(TypedDict, total=False):
    """Serializable state passed between LangGraph nodes.

    Database sessions and ORM objects deliberately stay outside this state so
    parallel branches never share a SQLAlchemy session.
    """

    ticket_id: int
    order_id: int | None
    ticket_content: str
    classification: dict[str, Any]
    classification_data: dict[str, Any]
    plan: dict[str, Any]
    execution_mode: str
    sequence_map: dict[str, int]
    order_context: dict[str, Any]
    knowledge_context: dict[str, Any]
    knowledge_sources: list[dict[str, Any]]
    case_manager_step: int
    case_history: list[dict[str, Any]]
    case_decision: dict[str, Any]
    specialist_agent: str
    evidence_gate: dict[str, Any]
    pending_question: str | None
    resume_state: dict[str, Any]
    trace_sequence: int
    review_package: dict[str, Any]
    decision: dict[str, Any]
    reply: str
    reply_source: str
    action_result: dict[str, Any]
    graph_stage: str


def _empty_order_context() -> dict[str, Any]:
    return {
        "order_found": False,
        "order_no": None,
        "product_name": None,
        "order_status": None,
        "shipped_at": None,
        "promised_delivery_at": None,
        "latest_logistics_status": None,
        "latest_logistics_event": None,
        "occurred_at": None,
        "timeline": [],
        "first_collected_at": None,
        "stagnant_hours": None,
        "delay_hours": 0.0,
        "is_overdue": False,
        "anomaly_type": None,
        "conflicts": [],
        "evidence_refs": [],
    }


def _empty_knowledge_context(*, required: bool = False) -> dict[str, Any]:
    return {"source_count": 0, "sources": [], "retrieval_required": required}


def _sequence_map(intent: str, execution_mode: str) -> dict[str, int]:
    if intent == "logistics_query":
        return {"supervisor": 1, "commerce_evidence": 2, "risk_control": 3, "reply": 4}
    if intent == "delivery_delay_compensation":
        evidence_end = 2 if execution_mode == "langgraph_parallel" else 3
        mapping = {
            "supervisor": 1,
            "commerce_evidence": 2,
            "knowledge": 2 if execution_mode == "langgraph_parallel" else 3,
        }
        mapping.update(risk_control=evidence_end + 1, reply=evidence_end + 2)
        return mapping
    if intent == "refund_risk_review":
        return {"supervisor": 1}
    return {"supervisor": 1, "risk_control": 2, "reply": 3}


def build_ticket_workflow(db: Session, ticket: Ticket):
    """Build the real LangGraph StateGraph used for one ticket execution."""
    def supervisor(state: TicketWorkflowState) -> TicketWorkflowState:
        if state.get("resume_state"):
            restored = dict(state["resume_state"])
            restored.update(
                ticket_content=state["ticket_content"],
                pending_question=None,
                graph_stage="resumed",
            )
            ticket.status = "processing"
            return restored

        provider = get_provider("supervisor") or get_provider("dispatcher")
        classification_box: dict[str, ClassificationResult] = {}
        plan_box: dict[str, dict[str, Any]] = {}

        def execute() -> dict[str, Any]:
            classification = classify_ticket(state["ticket_content"])
            plan = _execution_plan(classification)
            classification_box["value"] = classification
            plan_box["value"] = plan
            return {
                **asdict(classification),
                **plan,
                "workflow_engine": "langgraph_state_graph",
            }

        classification_data = _trace(
            db,
            ticket=ticket,
            sequence=1,
            agent_name="supervisor",
            provider=provider.name if provider else "rules",
            model=provider.model if provider else None,
            input_data={"ticket_content": state["ticket_content"]},
            execute=execute,
        )
        classification = classification_box["value"]
        plan = plan_box["value"]
        execution_mode = "agent_loop" if plan.get("agent_loop") else "langgraph_serial"

        ticket.intent = classification.intent
        ticket.priority = classification.priority
        ticket.risk_level = classification.risk_level
        ticket.status = "processing"
        customer_message_count = db.scalar(
            select(func.count(TicketMessage.id)).where(
                TicketMessage.ticket_id == ticket.id,
                TicketMessage.sender_type == "customer",
            )
        ) or 0
        initial_gate = evaluate_evidence(
            [],
            ticket_content=state["ticket_content"],
            source_count=0,
            retrieval_required=settings.rag_enabled,
            customer_message_count=customer_message_count,
            pending_question=None,
            step=0,
            scenario=("delivery_delay" if classification.intent == "delivery_delay_compensation" else "refund"),
        )
        return {
            "classification": asdict(classification),
            "classification_data": classification_data,
            "plan": plan,
            "execution_mode": execution_mode,
            "sequence_map": _sequence_map(classification.intent, execution_mode),
            "order_context": _empty_order_context(),
            "knowledge_context": _empty_knowledge_context(required=settings.rag_enabled),
            "knowledge_sources": [],
            "case_manager_step": 0,
            "case_history": [],
            "case_decision": {},
            "specialist_agent": plan.get("delegated_agent") or "",
            "evidence_gate": initial_gate.model_dump(),
            "pending_question": None,
            "trace_sequence": 2,
            "graph_stage": "dispatched",
        }

    def select_route(state: TicketWorkflowState) -> str | list[str]:
        route = state["plan"]["route"]
        if state.get("graph_stage") == "resumed":
            return "evidence_gate"
        if route == "logistics_fast_path":
            return "order_logistics_fast"
        if route == "refund_agent_investigation":
            return "refund_investigation_agent"
        if route == "logistics_agent_investigation":
            return "logistics_resolution_agent"
        return "risk_control"

    def order_logistics_fast(state: TicketWorkflowState) -> TicketWorkflowState:
        result = _trace(
            db,
            ticket=ticket,
            sequence=state["sequence_map"]["commerce_evidence"],
            agent_name="commerce_evidence_skill",
            provider="database",
            model=None,
            input_data={
                "operations": ["get_order", "analyze_delivery_timeline"],
                "order_id": state["order_id"],
                "intent": state["classification"]["intent"],
                "route": state["plan"]["route"],
                "execution_mode": state["execution_mode"],
            },
            execute=lambda: execute_commerce_evidence_skill(
                db,
                operations=["get_order", "analyze_delivery_timeline"],
                ticket_id=state["ticket_id"],
                order_id=state["order_id"],
            ),
        )
        return {"order_context": {**_empty_order_context(), **result["data"]}}

    def run_specialist_agent(
        state: TicketWorkflowState, *, agent_name: str, scenario: str
    ) -> TicketWorkflowState:
        """Plan one action while keeping data access behind shared Skills."""
        provider_key = "refund_investigation" if scenario == "refund" else "logistics_resolution"
        provider = get_provider(provider_key) or get_provider("case_manager")
        gate = EvidenceGateResult.model_validate(state["evidence_gate"])
        decision_box: dict[str, Any] = {}

        def execute() -> dict[str, Any]:
            decision, source, fallback_reason = choose_case_action(
                state["ticket_content"],
                state["case_history"],
                gate,
                step=state["case_manager_step"],
                scenario=scenario,
            )
            payload = {
                **decision.model_dump(),
                "decision_source": source,
                "step": state["case_manager_step"],
            }
            if fallback_reason:
                payload["fallback_reason"] = fallback_reason
            decision_box["value"] = payload
            return payload

        result = _trace(
            db,
            ticket=ticket,
            sequence=state["trace_sequence"],
            agent_name=agent_name,
            provider=provider.name if provider else "rules",
            model=provider.model if provider else None,
            input_data={
                "goal": (
                    "准备可供主管复核的退款争议事实包"
                    if scenario == "refund"
                    else "准备可供规则引擎审批的延迟补偿事实包"
                ),
                "step": state["case_manager_step"],
                "observations": state["case_history"],
                "evidence_gate": state["evidence_gate"],
                "available_skills": SKILL_CATALOG,
                "allowed_operations": sorted(READ_ONLY_CASE_TOOLS),
                "allowed_actions": ["ask_customer", "finish"],
            },
            execute=execute,
        )
        return {
            "case_decision": decision_box.get("value", result),
            "case_manager_step": state["case_manager_step"] + 1,
            "trace_sequence": state["trace_sequence"] + 1,
        }

    def logistics_resolution_agent(state: TicketWorkflowState) -> TicketWorkflowState:
        return run_specialist_agent(
            state, agent_name="logistics_resolution_agent", scenario="delivery_delay"
        )

    def refund_investigation_agent(state: TicketWorkflowState) -> TicketWorkflowState:
        return run_specialist_agent(
            state, agent_name="refund_investigation_agent", scenario="refund"
        )

    def after_specialist_agent(state: TicketWorkflowState) -> str:
        return "evidence_gate" if state["case_decision"]["action"] == "finish" else "case_action"

    def case_action(state: TicketWorkflowState) -> TicketWorkflowState:
        """Execute a registered read-only tool or persist a customer question."""
        decision = state["case_decision"]
        action = decision["action"]
        history = list(state["case_history"])
        update: TicketWorkflowState = {"trace_sequence": state["trace_sequence"] + 1}

        if action == "ask_customer":
            question = decision.get("question") or "请补充完成退款复核所需的材料。"
            observation = {
                "action": action,
                "ok": True,
                "summary": "已生成客户补充材料请求",
                "data": {"question": question},
            }
            _trace(
                db,
                ticket=ticket,
                sequence=state["trace_sequence"],
                agent_name="case_action_ask_customer",
                provider="workflow",
                model=None,
                input_data={"question": question},
                execute=lambda: observation,
            )
            history.append(observation)
            update["pending_question"] = question
        else:
            arguments = decision.get("arguments") or {}
            skill_name = skill_for_action(action)
            provider_name = "chroma" if skill_name == "policy_retrieval" else "database"
            result = _trace(
                db,
                ticket=ticket,
                sequence=state["trace_sequence"],
                agent_name=f"{skill_name}_skill",
                provider=provider_name,
                model=None,
                input_data={
                    "operation": action,
                    "arguments": arguments,
                    "read_only": True,
                    "requested_by": state["specialist_agent"],
                },
                execute=lambda: execute_agent_skill(
                    db,
                    action=action,
                    ticket_id=state["ticket_id"],
                    order_id=state["order_id"],
                    arguments=arguments,
                    policy_category=(
                        "logistics"
                        if state["classification"]["intent"] == "delivery_delay_compensation"
                        else "after_sales"
                    ),
                ),
            )
            observation = {"action": action, **result}
            history.append(observation)
            data = result.get("data", {})
            if action == "get_order":
                update["order_context"] = {**state["order_context"], **data}
            elif action == "analyze_delivery_timeline":
                update["order_context"] = {**state["order_context"], **data}
            elif action == "search_policy":
                combined = {
                    row["chunk_id"]: row
                    for row in [*state["knowledge_sources"], *data.get("sources", [])]
                }
                merged = sorted(combined.values(), key=lambda row: row["score"], reverse=True)[:3]
                update["knowledge_sources"] = merged
                update["knowledge_context"] = {
                    "source_count": len(merged),
                    "sources": merged,
                    "retrieval_required": settings.rag_enabled,
                }

        update["case_history"] = history
        update["graph_stage"] = "case_action_completed"
        return update

    def evidence_gate(state: TicketWorkflowState) -> TicketWorkflowState:
        customer_message_count = db.scalar(
            select(func.count(TicketMessage.id)).where(
                TicketMessage.ticket_id == ticket.id,
                TicketMessage.sender_type == "customer",
            )
        ) or 0
        gate = _trace(
            db,
            ticket=ticket,
            sequence=state["trace_sequence"],
            agent_name="evidence_gate",
            provider="rules",
            model=None,
            input_data={
                "step": state["case_manager_step"],
                "customer_message_count": customer_message_count,
                "pending_question": state.get("pending_question"),
            },
            execute=lambda: evaluate_evidence(
                state["case_history"],
                ticket_content=state["ticket_content"],
                source_count=state["knowledge_context"]["source_count"],
                retrieval_required=state["knowledge_context"]["retrieval_required"],
                customer_message_count=customer_message_count,
                pending_question=state.get("pending_question"),
                step=state["case_manager_step"],
                scenario=(
                    "delivery_delay"
                    if state["classification"]["intent"] == "delivery_delay_compensation"
                    else "refund"
                ),
            ).model_dump(),
        )
        return {"evidence_gate": gate, "trace_sequence": state["trace_sequence"] + 1}

    def after_evidence_gate(state: TicketWorkflowState) -> str:
        disposition = state["evidence_gate"]["disposition"]
        if disposition == "waiting_customer":
            return "wait_customer"
        if disposition in {"ready", "budget_exhausted"}:
            return (
                "refund_review_analyst"
                if state["classification"]["intent"] == "refund_risk_review"
                else "risk_control"
            )
        return state["specialist_agent"]

    def wait_customer(_: TicketWorkflowState) -> TicketWorkflowState:
        return {"graph_stage": "waiting_customer"}

    def refund_review_analyst(state: TicketWorkflowState) -> TicketWorkflowState:
        provider = get_provider("refund_analyst")
        sources = _sources_from_payload(state["knowledge_sources"])
        review_package = _trace(
            db,
            ticket=ticket,
            sequence=state["trace_sequence"],
            agent_name="refund_review_analyst",
            provider=provider.name if provider else "template",
            model=provider.model if provider else None,
            input_data={
                "ticket_content": state["ticket_content"],
                "order_found": state["order_context"]["order_found"],
                "knowledge_source_count": len(sources),
                "case_history": state["case_history"],
                "evidence_gate": state["evidence_gate"],
                "route": state["plan"]["route"],
            },
            execute=lambda: analyse_refund_review(
                state["ticket_content"], state["order_context"], sources
            ),
        )
        review_package["case_history"] = state["case_history"]
        review_package["evidence_gate"] = state["evidence_gate"]
        return {"review_package": review_package, "trace_sequence": state["trace_sequence"] + 1}

    def risk_control(state: TicketWorkflowState) -> TicketWorkflowState:
        classification = ClassificationResult(**state["classification"])
        decision = _trace(
            db,
            ticket=ticket,
            sequence=(
                state["trace_sequence"]
                if state["classification"]["intent"] in {"refund_risk_review", "delivery_delay_compensation"}
                else state["sequence_map"]["risk_control"]
            ),
            agent_name="risk_control",
            provider="rules",
            model=None,
            input_data={
                "classification": state["classification_data"],
                "route": state["plan"]["route"],
                "order_found": state["order_context"]["order_found"],
                "knowledge_source_count": state["knowledge_context"]["source_count"],
                "knowledge_retrieval_required": state["knowledge_context"]["retrieval_required"],
                "refund_review_package_available": bool(state.get("review_package")),
            },
            execute=lambda: _risk_decision(
                classification, state["order_context"], state["knowledge_context"]
            ),
        )
        update: TicketWorkflowState = {"decision": decision}
        if state["classification"]["intent"] in {"refund_risk_review", "delivery_delay_compensation"}:
            update["trace_sequence"] = state["trace_sequence"] + 1
        return update

    def reply(state: TicketWorkflowState) -> TicketWorkflowState:
        provider = get_provider("reply")
        sources = _sources_from_payload(state["knowledge_sources"])
        reply_box: dict[str, Any] = {}

        def execute() -> dict[str, Any]:
            draft, action_result = _draft_reply(
                state["decision"], state["order_context"], state.get("review_package")
            )
            content, reply_source = generate_grounded_reply(
                state["ticket_content"], draft, sources
            )
            reply_box.update(
                reply=content,
                reply_source=reply_source,
                action_result=action_result,
            )
            return {
                "reply": content,
                "reply_source": reply_source,
                "used_knowledge": bool(sources),
            }

        _trace(
            db,
            ticket=ticket,
            sequence=(
                state["trace_sequence"]
                if state["classification"]["intent"] in {"refund_risk_review", "delivery_delay_compensation"}
                else state["sequence_map"]["reply"]
            ),
            agent_name="reply",
            provider=provider.name if provider else "template",
            model=provider.model if provider else None,
            input_data={
                "action": state["decision"]["action"],
                "route": state["plan"]["route"],
                "knowledge_source_count": len(sources),
            },
            execute=execute,
        )
        action_result = reply_box["action_result"]
        action_result["reply_source"] = reply_box["reply_source"]
        action_result["knowledge_sources"] = state["knowledge_sources"]
        return {
            "reply": reply_box["reply"],
            "reply_source": reply_box["reply_source"],
            "action_result": action_result,
            "graph_stage": "completed",
        }

    graph = StateGraph(TicketWorkflowState)
    graph.add_node("supervisor", supervisor)
    graph.add_node("order_logistics_fast", order_logistics_fast)
    graph.add_node("logistics_resolution_agent", logistics_resolution_agent)
    graph.add_node("refund_investigation_agent", refund_investigation_agent)
    graph.add_node("case_action", case_action)
    graph.add_node("evidence_gate", evidence_gate)
    graph.add_node("wait_customer", wait_customer)
    graph.add_node("refund_review_analyst", refund_review_analyst)
    graph.add_node("risk_control", risk_control)
    graph.add_node("reply", reply)
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        select_route,
        [
            "order_logistics_fast",
            "logistics_resolution_agent",
            "refund_investigation_agent",
            "evidence_gate",
            "risk_control",
        ],
    )
    graph.add_edge("order_logistics_fast", "risk_control")
    graph.add_conditional_edges(
        "logistics_resolution_agent", after_specialist_agent, ["case_action", "evidence_gate"]
    )
    graph.add_conditional_edges(
        "refund_investigation_agent", after_specialist_agent, ["case_action", "evidence_gate"]
    )
    graph.add_edge("case_action", "evidence_gate")
    graph.add_conditional_edges(
        "evidence_gate",
        after_evidence_gate,
        ["logistics_resolution_agent", "refund_investigation_agent", "refund_review_analyst", "risk_control", "wait_customer"],
    )
    graph.add_edge("wait_customer", END)
    graph.add_edge("refund_review_analyst", "risk_control")
    graph.add_edge("risk_control", "reply")
    graph.add_edge("reply", END)
    return graph.compile()


def orchestrate_ticket(db: Session, ticket: Ticket) -> Ticket:
    """Run the LangGraph workflow and persist its business-side effects."""
    if ticket.status in {"resolved", "pending_approval", "escalated"}:
        return ticket

    case_state = db.scalar(select(CaseAgentState).where(CaseAgentState.ticket_id == ticket.id))
    customer_contents = list(
        db.scalars(
            select(TicketMessage.content)
            .where(TicketMessage.ticket_id == ticket.id, TicketMessage.sender_type == "customer")
            .order_by(TicketMessage.created_at.asc(), TicketMessage.id.asc())
        ).all()
    )
    combined_content = "\n".join(customer_contents) or ticket.content
    resume_state = case_state.state_data if case_state and case_state.status == "active" else None

    workflow = build_ticket_workflow(db, ticket)
    result: TicketWorkflowState = workflow.invoke(
        {
            "ticket_id": ticket.id,
            "order_id": ticket.order_id,
            "ticket_content": combined_content,
            "resume_state": resume_state,
        },
        config={"configurable": {"thread_id": f"ticket-{ticket.id}"}},
    )

    if result.get("graph_stage") == "waiting_customer":
        persisted = {
            key: result[key]
            for key in (
                "classification",
                "classification_data",
                "plan",
                "execution_mode",
                "sequence_map",
                "order_context",
                "knowledge_context",
                "knowledge_sources",
                "case_manager_step",
                "case_history",
                "case_decision",
                "specialist_agent",
                "evidence_gate",
                "pending_question",
                "trace_sequence",
            )
            if key in result
        }
        if case_state:
            case_state.status = "waiting_customer"
            case_state.state_data = persisted
            case_state.pending_question = result["pending_question"]
        else:
            case_state = CaseAgentState(
                ticket_id=ticket.id,
                status="waiting_customer",
                goal=(
                    "准备可供主管复核的退款争议事实包"
                    if result["classification"]["intent"] == "refund_risk_review"
                    else "准备可供规则引擎审批的延迟补偿事实包"
                ),
                state_data=persisted,
                pending_question=result["pending_question"],
            )
            db.add(case_state)
        ticket.status = "waiting_customer"
        db.add(TicketMessage(ticket_id=ticket.id, sender_type="assistant", content=result["pending_question"]))
        db.add(
            AuditLog(
                ticket_id=ticket.id,
                action="request_customer_evidence",
                operator_type=result["specialist_agent"],
                input_data={"evidence_gate": result["evidence_gate"]},
                output_data={"question": result["pending_question"]},
            )
        )
        db.commit()
        return ticket

    decision = result["decision"]
    action_result = result["action_result"]
    if decision["action"] == "request_coupon_approval":
        db.add(
            ApprovalTask(
                ticket_id=ticket.id,
                task_type="coupon_compensation",
                proposed_data=action_result.copy(),
            )
        )
    elif decision["action"] == "escalate_to_supervisor":
        db.add(
            ApprovalTask(
                ticket_id=ticket.id,
                task_type="refund_review",
                status="pending",
                proposed_data=action_result.copy(),
            )
        )

    ticket.status = decision["status"]
    if result["classification"]["intent"] in {"refund_risk_review", "delivery_delay_compensation"}:
        if not case_state:
            case_state = CaseAgentState(
                ticket_id=ticket.id,
                goal=(
                    "准备可供主管复核的退款争议事实包"
                    if result["classification"]["intent"] == "refund_risk_review"
                    else "准备可供规则引擎审批的延迟补偿事实包"
                ),
                state_data={},
            )
            db.add(case_state)
        case_state.status = "completed"
        case_state.pending_question = None
        case_state.state_data = {
            "case_manager_step": result["case_manager_step"],
            "case_history": result["case_history"],
            "evidence_gate": result["evidence_gate"],
            "trace_sequence": result["trace_sequence"],
        }
    db.add(TicketMessage(ticket_id=ticket.id, sender_type="assistant", content=result["reply"]))
    db.add(
        AuditLog(
            ticket_id=ticket.id,
            action=decision["action"],
            operator_type="langgraph",
            input_data={
                "classification": result["classification"],
                "orchestration_plan": result["plan"],
                "execution_mode": result["execution_mode"],
                "risk_decision": decision,
            },
            output_data=action_result,
        )
    )
    db.commit()
    return ticket
