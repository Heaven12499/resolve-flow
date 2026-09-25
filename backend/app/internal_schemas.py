from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class TicketSnapshot(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=2, max_length=4000)


class OrderSnapshot(BaseModel):
    order_no: str = Field(min_length=1, max_length=64)
    product_name: str | None = Field(default=None, max_length=255)
    amount: Decimal
    status: str = Field(min_length=1, max_length=30)
    shipped_at: datetime | None = None
    promised_delivery_at: datetime | None = None


class LogisticsEventSnapshot(BaseModel):
    event_id: int | None = None
    status: str = Field(min_length=1, max_length=30)
    description: str = Field(min_length=1, max_length=500)
    occurred_at: datetime


class MessageSnapshot(BaseModel):
    sender_type: Literal["customer", "assistant", "agent"]
    content: str = Field(min_length=1, max_length=4000)
    created_at: datetime | None = None


class EvidenceSnapshot(BaseModel):
    evidence_id: int | None = None
    file_name: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=100)
    storage_uri: str = Field(min_length=3, max_length=500)
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


class CaseAnalysisRequest(BaseModel):
    task_id: str = Field(min_length=1, max_length=64)
    ticket_id: int = Field(gt=0)
    business_version: int = Field(ge=0)
    ticket: TicketSnapshot
    order: OrderSnapshot
    logistics_timeline: list[LogisticsEventSnapshot] = Field(default_factory=list, max_length=200)
    messages: list[MessageSnapshot] = Field(default_factory=list, max_length=100)
    evidence: list[EvidenceSnapshot] = Field(default_factory=list, max_length=20)


class EvidenceReference(BaseModel):
    type: Literal["tracking", "attachment", "policy"]
    reference: str


class CaseAnalysisResult(BaseModel):
    task_id: str
    ticket_id: int
    business_version: int
    status: Literal["SUCCEEDED"] = "SUCCEEDED"
    intent: Literal[
        "logistics_query",
        "delivery_delay_compensation",
        "refund_risk_review",
        "other",
    ]
    priority: Literal["low", "medium", "high"]
    risk_level: Literal["low", "medium", "high"]
    recommended_action: Literal[
        "QUERY_LOGISTICS",
        "REQUEST_COUPON_APPROVAL",
        "ESCALATE_REFUND_REVIEW",
        "ESCALATE_TO_HUMAN",
    ]
    suggested_coupon_amount: int | None = Field(default=None, ge=1, le=100)
    reply_draft: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0, le=1)
    requires_human_approval: bool
    evidence: list[EvidenceReference]
    model_source: str
    fallback_reason: str | None = None
