"""Reusable, bounded Skills shared by specialist investigation Agents.

Agents own the goal and decide which capability to use next.  Skills own a
small, testable procedure and delegate atomic I/O to the read-only tool layer.
"""

from typing import Any, Literal

from sqlalchemy.orm import Session

from app.services.case_tools import execute_read_only_tool


SkillName = Literal["commerce_evidence", "policy_retrieval"]

COMMERCE_EVIDENCE_OPERATIONS = {
    "get_order",
    "analyze_delivery_timeline",
    "get_ticket_messages",
    "inspect_customer_evidence",
}

SKILL_CATALOG: dict[str, dict[str, Any]] = {
    "commerce_evidence": {
        "description": "标准化采集订单、物流、对话和客户材料证据",
        "operations": sorted(COMMERCE_EVIDENCE_OPERATIONS),
        "read_only": True,
    },
    "policy_retrieval": {
        "description": "按业务场景检索、过滤并返回带来源的政策证据",
        "operations": ["search_policy"],
        "read_only": True,
    },
}


def execute_commerce_evidence_skill(
    db: Session,
    *,
    operations: list[str],
    ticket_id: int,
    order_id: int | None,
) -> dict[str, Any]:
    """Collect one or more commerce facts through a single reusable Skill."""
    if not operations or any(action not in COMMERCE_EVIDENCE_OPERATIONS for action in operations):
        raise ValueError("commerce_evidence contains an unsupported operation")

    evidence: dict[str, dict[str, Any]] = {}
    normalized: dict[str, Any] = {}
    for action in operations:
        result = execute_read_only_tool(
            db,
            action=action,
            ticket_id=ticket_id,
            order_id=order_id,
            arguments={},
        )
        evidence[action] = result
        normalized.update(result.get("data", {}))

    return {
        "ok": all(item.get("ok", False) for item in evidence.values()),
        "summary": f"已通过交易证据 Skill 执行 {len(operations)} 项只读核验",
        "skill": "commerce_evidence",
        "operations": operations,
        "read_only": True,
        "evidence": evidence,
        "data": normalized,
    }


def skill_for_action(action: str) -> SkillName:
    if action in COMMERCE_EVIDENCE_OPERATIONS:
        return "commerce_evidence"
    if action == "search_policy":
        return "policy_retrieval"
    raise ValueError(f"action is not provided by a registered Skill: {action}")


def execute_agent_skill(
    db: Session,
    *,
    action: str,
    ticket_id: int,
    order_id: int | None,
    arguments: dict[str, Any],
    policy_category: str,
) -> dict[str, Any]:
    """Execute one operation through its owning Skill and expose provenance."""
    skill_name = skill_for_action(action)
    if skill_name == "commerce_evidence":
        result = execute_commerce_evidence_skill(
            db,
            operations=[action],
            ticket_id=ticket_id,
            order_id=order_id,
        )
        return {
            **result,
            "operation": action,
            "summary": result["evidence"][action]["summary"],
            "ok": result["evidence"][action]["ok"],
        }

    tool_arguments = dict(arguments)
    tool_arguments["category"] = policy_category
    result = execute_read_only_tool(
        db,
        action=action,
        ticket_id=ticket_id,
        order_id=order_id,
        arguments=tool_arguments,
    )
    return {
        **result,
        "skill": skill_name,
        "operation": action,
        "read_only": True,
    }
