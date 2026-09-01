from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TicketCreate(BaseModel):
    order_no: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=2, max_length=2000)
    title: str | None = Field(default=None, max_length=255)


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sender_type: str
    content: str
    created_at: datetime


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    operator_type: str
    input_data: dict[str, Any] | None
    output_data: dict[str, Any] | None
    created_at: datetime


class ApprovalTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_type: str
    status: str
    proposed_data: dict[str, Any]
    decision_data: dict[str, Any] | None
    created_at: datetime
    decided_at: datetime | None


class TicketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_no: str
    customer_id: int
    order_id: int | None
    title: str
    content: str
    intent: str | None
    priority: str
    risk_level: str
    status: str
    created_at: datetime
    updated_at: datetime


class TicketDetail(TicketRead):
    messages: list[MessageRead] = Field(default_factory=list)
    audit_logs: list[AuditLogRead] = Field(default_factory=list)
    approval_tasks: list[ApprovalTaskRead] = Field(default_factory=list)


class LogisticsEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    description: str
    occurred_at: datetime


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_no: str
    customer_id: int
    product_name: str
    amount: Decimal
    status: str
    created_at: datetime


class OrderDetail(OrderRead):
    logistics_events: list[LogisticsEventRead] = Field(default_factory=list)


class KnowledgeDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    category: str
    version: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class KnowledgeReindexResult(BaseModel):
    document_count: int
    chunk_count: int
    collection_name: str


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    limit: int = Field(default=3, ge=1, le=10)


class KnowledgeSearchResult(BaseModel):
    chunk_id: int
    document_id: int
    title: str
    category: str
    version: str
    content: str
    score: float
