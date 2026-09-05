"""Observable, role-based workflow orchestration for ticket processing.

Only the router, refund-review analyst, and response units are Agents.
Order/logistics and knowledge retrieval are deterministic Skills; risk and
action gating belong to the Rule Engine. This keeps model output outside the
high-risk decision boundary.
"""

from dataclasses import asdict
from time import perf_counter
from types import SimpleNamespace
from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models import AgentRun, ApprovalTask, AuditLog, LogisticsEvent, Order, Ticket, TicketMessage, utc_now
from app.services.knowledge_service import KnowledgeSource, retrieve_knowledge
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


def _read_order_context(db: Session, order_id: int | None) -> dict[str, Any]:
    order = db.get(Order, order_id) if order_id else None
    latest_event = None
    if order:
        latest_event = db.scalar(
            select(LogisticsEvent)
            .where(LogisticsEvent.order_id == order.id)
            .order_by(LogisticsEvent.occurred_at.desc())
            .limit(1)
        )
    return {
        "order_found": bool(order),
        "order_no": order.order_no if order else None,
        "product_name": order.product_name if order else None,
        "order_status": order.status if order else None,
        "latest_logistics_status": latest_event.status if latest_event else None,
        "latest_logistics_event": latest_event.description if latest_event else None,
    }


def _source_payload(sources: list[KnowledgeSource]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": source.chunk_id,
            "document_id": source.document_id,
            "title": source.title,
            "version": source.version,
            "category": source.category,
            "score": round(source.score, 4),
            "content": source.content,
        }
        for source in sources
    ]


def _sources_from_payload(rows: list[dict[str, Any]]) -> list[KnowledgeSource]:
    """Rehydrate typed sources at the boundary of model-facing functions."""
    return [KnowledgeSource(**row) for row in rows]


def _knowledge_category(intent: str) -> str | None:
    if intent in {"logistics_query", "delivery_delay_compensation"}:
        return "logistics"
    if intent == "refund_risk_review":
        return "after_sales"
    return None


def _execution_plan(classification: ClassificationResult) -> dict[str, Any]:
    """Let the dispatcher select a minimal, safe workflow for each intent.

    The plan is deterministic because routing and risk authority must remain in
    backend code.  An LLM may classify the request, but it may not decide which
    safety gate can be bypassed.
    """
    if classification.intent == "logistics_query":
        return {
            "route": "logistics_fast_path",
            "reason": "仅需核验订单实时物流，不涉及权益或售后政策判断。",
            "next_agents": ["order_logistics", "risk_control", "reply"],
            "fanout_groups": [],
            "skipped_agents": [
                {"agent_name": "knowledge", "reason": "订单物流系统已提供实时事实，无需检索政策库。"},
            ],
        }
    if classification.intent == "delivery_delay_compensation":
        return {
            "route": "compensation_with_approval",
            "reason": "需同时核验物流事实与补偿规则，随后由风控发起人工审批。",
            "next_agents": ["order_logistics", "knowledge", "risk_control", "reply"],
            "fanout_groups": [
                {"agents": ["order_logistics", "knowledge"], "join_agent": "risk_control"},
            ],
            "skipped_agents": [],
        }
    if classification.intent == "refund_risk_review":
        return {
            "route": "high_risk_refund_review",
            "reason": "退款属于高风险事项，汇集订单事实和售后规则后生成主管复核建议包。",
            "next_agents": ["order_logistics", "knowledge", "refund_review_analyst", "risk_control", "reply"],
            "fanout_groups": [
                {"agents": ["order_logistics", "knowledge"], "join_agent": "refund_review_analyst"},
            ],
            "skipped_agents": [],
        }
    return {
        "route": "human_handoff",
        "reason": "意图置信不足或不在自动处置范围，直接进入人工兜底。",
        "next_agents": ["risk_control", "reply"],
        "fanout_groups": [],
        "skipped_agents": [
            {"agent_name": "order_logistics", "reason": "当前问题不需要订单或物流核验。"},
            {"agent_name": "knowledge", "reason": "当前问题没有匹配的自动处置政策。"},
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
        "latest_logistics_status": None,
        "latest_logistics_event": None,
    }


def _empty_knowledge_context(*, required: bool = False) -> dict[str, Any]:
    return {"source_count": 0, "sources": [], "retrieval_required": required}


def _sequence_map(intent: str, execution_mode: str) -> dict[str, int]:
    if intent == "logistics_query":
        return {"dispatcher": 1, "order_logistics": 2, "risk_control": 3, "reply": 4}
    if intent in {"delivery_delay_compensation", "refund_risk_review"}:
        evidence_end = 2 if execution_mode == "langgraph_parallel" else 3
        mapping = {
            "dispatcher": 1,
            "order_logistics": 2,
            "knowledge": 2 if execution_mode == "langgraph_parallel" else 3,
        }
        if intent == "refund_risk_review":
            mapping.update(
                refund_review_analyst=evidence_end + 1,
                risk_control=evidence_end + 2,
                reply=evidence_end + 3,
            )
        else:
            mapping.update(risk_control=evidence_end + 1, reply=evidence_end + 2)
        return mapping
    return {"dispatcher": 1, "risk_control": 2, "reply": 3}


def build_ticket_workflow(db: Session, ticket: Ticket):
    """Build the real LangGraph StateGraph used for one ticket execution."""
    ticket_reference = SimpleNamespace(id=ticket.id)
    worker_factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)

    def dispatcher(state: TicketWorkflowState) -> TicketWorkflowState:
        provider = get_provider("dispatcher")
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
            agent_name="dispatcher",
            provider=provider.name if provider else "rules",
            model=provider.model if provider else None,
            input_data={"ticket_content": state["ticket_content"]},
            execute=execute,
        )
        classification = classification_box["value"]
        plan = plan_box["value"]
        has_parallel_evidence = bool(plan.get("fanout_groups")) and db.get_bind().dialect.name == "mysql"
        execution_mode = "langgraph_parallel" if has_parallel_evidence else "langgraph_serial"

        ticket.intent = classification.intent
        ticket.priority = classification.priority
        ticket.risk_level = classification.risk_level
        ticket.status = "processing"
        if has_parallel_evidence:
            # Worker sessions need the ticket and dispatcher trace committed
            # before their AgentRun rows reference them.
            db.commit()

        return {
            "classification": asdict(classification),
            "classification_data": classification_data,
            "plan": plan,
            "execution_mode": execution_mode,
            "sequence_map": _sequence_map(classification.intent, execution_mode),
            "order_context": _empty_order_context(),
            "knowledge_context": _empty_knowledge_context(),
            "knowledge_sources": [],
            "graph_stage": "dispatched",
        }

    def select_route(state: TicketWorkflowState) -> str | list[str]:
        route = state["plan"]["route"]
        if route == "logistics_fast_path":
            return "order_logistics_fast"
        if state["execution_mode"] == "langgraph_parallel":
            return ["order_logistics", "knowledge"]
        if route in {"compensation_with_approval", "high_risk_refund_review"}:
            return "evidence_serial"
        return "risk_control"

    def run_parallel_branch(
        state: TicketWorkflowState, agent_name: str
    ) -> TicketWorkflowState:
        with worker_factory() as worker_db:
            try:
                if agent_name == "order_logistics":
                    result = _trace(
                        worker_db,
                        ticket=ticket_reference,
                        sequence=state["sequence_map"][agent_name],
                        agent_name=agent_name,
                        provider="database",
                        model=None,
                        input_data={
                            "order_id": state["order_id"],
                            "intent": state["classification"]["intent"],
                            "route": state["plan"]["route"],
                            "execution_mode": state["execution_mode"],
                        },
                        execute=lambda: _read_order_context(worker_db, state["order_id"]),
                    )
                    worker_db.commit()
                    return {"order_context": result}

                source_box: dict[str, list[KnowledgeSource]] = {}

                def execute_knowledge() -> dict[str, Any]:
                    sources = retrieve_knowledge(
                        worker_db,
                        state["ticket_content"],
                        category=_knowledge_category(state["classification"]["intent"]),
                    )
                    source_box["value"] = sources
                    return {
                        "source_count": len(sources),
                        "sources": _source_payload(sources),
                        "retrieval_required": settings.rag_enabled,
                    }

                result = _trace(
                    worker_db,
                    ticket=ticket_reference,
                    sequence=state["sequence_map"][agent_name],
                    agent_name=agent_name,
                    provider="chroma",
                    model=None,
                    input_data={
                        "query": state["ticket_content"],
                        "top_k": 3,
                        "category": _knowledge_category(state["classification"]["intent"]),
                        "route": state["plan"]["route"],
                        "execution_mode": state["execution_mode"],
                    },
                    execute=execute_knowledge,
                )
                worker_db.commit()
                return {
                    "knowledge_context": result,
                    "knowledge_sources": _source_payload(source_box["value"]),
                }
            except Exception as exc:
                worker_db.rollback()
                worker_db.add(
                    AgentRun(
                        ticket_id=state["ticket_id"],
                        sequence=state["sequence_map"][agent_name],
                        agent_name=agent_name,
                        status="failed",
                        provider="database" if agent_name == "order_logistics" else "chroma",
                        model=None,
                        input_data={
                            "route": state["plan"]["route"],
                            "execution_mode": state["execution_mode"],
                        },
                        error=type(exc).__name__,
                        finished_at=utc_now(),
                    )
                )
                worker_db.commit()
                if agent_name == "order_logistics":
                    failed_order = _empty_order_context()
                    failed_order["branch_error"] = type(exc).__name__
                    return {"order_context": failed_order}
                failed_knowledge = _empty_knowledge_context(required=settings.rag_enabled)
                failed_knowledge["branch_error"] = type(exc).__name__
                return {"knowledge_context": failed_knowledge, "knowledge_sources": []}

    def order_logistics(state: TicketWorkflowState) -> TicketWorkflowState:
        return run_parallel_branch(state, "order_logistics")

    def knowledge(state: TicketWorkflowState) -> TicketWorkflowState:
        return run_parallel_branch(state, "knowledge")

    def order_logistics_fast(state: TicketWorkflowState) -> TicketWorkflowState:
        result = _trace(
            db,
            ticket=ticket,
            sequence=state["sequence_map"]["order_logistics"],
            agent_name="order_logistics",
            provider="database",
            model=None,
            input_data={
                "order_id": state["order_id"],
                "intent": state["classification"]["intent"],
                "route": state["plan"]["route"],
                "execution_mode": state["execution_mode"],
            },
            execute=lambda: _read_order_context(db, state["order_id"]),
        )
        return {"order_context": result}

    def evidence_serial(state: TicketWorkflowState) -> TicketWorkflowState:
        order_context = _trace(
            db,
            ticket=ticket,
            sequence=state["sequence_map"]["order_logistics"],
            agent_name="order_logistics",
            provider="database",
            model=None,
            input_data={
                "order_id": state["order_id"],
                "intent": state["classification"]["intent"],
                "route": state["plan"]["route"],
                "execution_mode": state["execution_mode"],
            },
            execute=lambda: _read_order_context(db, state["order_id"]),
        )
        source_box: dict[str, list[KnowledgeSource]] = {}

        def execute_knowledge() -> dict[str, Any]:
            sources = retrieve_knowledge(
                db,
                state["ticket_content"],
                category=_knowledge_category(state["classification"]["intent"]),
            )
            source_box["value"] = sources
            return {
                "source_count": len(sources),
                "sources": _source_payload(sources),
                "retrieval_required": settings.rag_enabled,
            }

        knowledge_context = _trace(
            db,
            ticket=ticket,
            sequence=state["sequence_map"]["knowledge"],
            agent_name="knowledge",
            provider="chroma",
            model=None,
            input_data={
                "query": state["ticket_content"],
                "top_k": 3,
                "category": _knowledge_category(state["classification"]["intent"]),
                "route": state["plan"]["route"],
                "execution_mode": state["execution_mode"],
            },
            execute=execute_knowledge,
        )
        return {
            "order_context": order_context,
            "knowledge_context": knowledge_context,
            "knowledge_sources": _source_payload(source_box["value"]),
            "graph_stage": "evidence_joined",
        }

    def evidence_join(_: TicketWorkflowState) -> TicketWorkflowState:
        return {"graph_stage": "evidence_joined"}

    def after_evidence(state: TicketWorkflowState) -> str:
        if state["classification"]["intent"] == "refund_risk_review":
            return "refund_review_analyst"
        return "risk_control"

    def refund_review_analyst(state: TicketWorkflowState) -> TicketWorkflowState:
        provider = get_provider("refund_analyst")
        sources = _sources_from_payload(state["knowledge_sources"])
        review_package = _trace(
            db,
            ticket=ticket,
            sequence=state["sequence_map"]["refund_review_analyst"],
            agent_name="refund_review_analyst",
            provider=provider.name if provider else "template",
            model=provider.model if provider else None,
            input_data={
                "ticket_content": state["ticket_content"],
                "order_found": state["order_context"]["order_found"],
                "knowledge_source_count": len(sources),
                "route": state["plan"]["route"],
            },
            execute=lambda: analyse_refund_review(
                state["ticket_content"], state["order_context"], sources
            ),
        )
        return {"review_package": review_package}

    def risk_control(state: TicketWorkflowState) -> TicketWorkflowState:
        classification = ClassificationResult(**state["classification"])
        decision = _trace(
            db,
            ticket=ticket,
            sequence=state["sequence_map"]["risk_control"],
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
        return {"decision": decision}

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
            sequence=state["sequence_map"]["reply"],
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
    graph.add_node("dispatcher", dispatcher)
    graph.add_node("order_logistics_fast", order_logistics_fast)
    graph.add_node("order_logistics", order_logistics)
    graph.add_node("knowledge", knowledge)
    graph.add_node("evidence_serial", evidence_serial)
    graph.add_node("evidence_join", evidence_join)
    graph.add_node("refund_review_analyst", refund_review_analyst)
    graph.add_node("risk_control", risk_control)
    graph.add_node("reply", reply)
    graph.add_edge(START, "dispatcher")
    graph.add_conditional_edges(
        "dispatcher",
        select_route,
        [
            "order_logistics_fast",
            "order_logistics",
            "knowledge",
            "evidence_serial",
            "risk_control",
        ],
    )
    graph.add_edge("order_logistics_fast", "risk_control")
    graph.add_edge(["order_logistics", "knowledge"], "evidence_join")
    graph.add_edge("evidence_serial", "evidence_join")
    graph.add_conditional_edges(
        "evidence_join", after_evidence, ["refund_review_analyst", "risk_control"]
    )
    graph.add_edge("refund_review_analyst", "risk_control")
    graph.add_edge("risk_control", "reply")
    graph.add_edge("reply", END)
    return graph.compile()


def orchestrate_ticket(db: Session, ticket: Ticket) -> Ticket:
    """Run the LangGraph workflow and persist its business-side effects."""
    if ticket.status in {"resolved", "pending_approval", "escalated"}:
        return ticket

    workflow = build_ticket_workflow(db, ticket)
    result: TicketWorkflowState = workflow.invoke(
        {
            "ticket_id": ticket.id,
            "order_id": ticket.order_id,
            "ticket_content": ticket.content,
        },
        config={"configurable": {"thread_id": f"ticket-{ticket.id}"}},
    )
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
