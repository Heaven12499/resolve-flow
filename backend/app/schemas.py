from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TicketCreate(BaseModel):
    order_no: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=2, max_length=2000)
    title: str | None = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=300)


class AccessTokenRead(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    username: str
    role: str


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


class ApprovalDecision(BaseModel):
    reason: str | None = Field(default=None, max_length=300)


class ApprovalQueueItem(ApprovalTaskRead):
    ticket_id: int
    ticket_no: str
    ticket_title: str
    ticket_content: str
    ticket_status: str
    risk_level: str


class AgentRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sequence: int
    agent_name: str
    status: str
    provider: str
    model: str | None
    input_data: dict[str, Any] | None
    output_data: dict[str, Any] | None
    error: str | None
    duration_ms: int
    started_at: datetime
    finished_at: datetime | None


class AgentRunQueueItem(AgentRunRead):
    ticket_id: int
    ticket_no: str
    ticket_title: str
    ticket_status: str


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


class TicketProcessingJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    attempt_count: int
    last_error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class TicketDetail(TicketRead):
    messages: list[MessageRead] = Field(default_factory=list)
    audit_logs: list[AuditLogRead] = Field(default_factory=list)
    approval_tasks: list[ApprovalTaskRead] = Field(default_factory=list)
    agent_runs: list[AgentRunRead] = Field(default_factory=list)
    processing_job: TicketProcessingJobRead | None = None


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
    content: str
    category: str
    version: str
    is_active: bool
    source_name: str | None
    source_type: str
    source_metadata: dict[str, Any] | None
    content_hash: str | None
    ingestion_status: str
    created_at: datetime
    updated_at: datetime


class KnowledgeDocumentCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    content: str = Field(min_length=10, max_length=10000)
    category: str = Field(min_length=2, max_length=50)
    version: str = Field(default="v1.0", min_length=1, max_length=50)
    is_active: bool = True


class KnowledgeDocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    content: str | None = Field(default=None, min_length=10, max_length=10000)
    category: str | None = Field(default=None, min_length=2, max_length=50)
    version: str | None = Field(default=None, min_length=1, max_length=50)
    is_active: bool | None = None


class KnowledgeReindexResult(BaseModel):
    document_count: int
    chunk_count: int
    collection_name: str
    generation: str


class KnowledgeIngestionResult(BaseModel):
    document: KnowledgeDocumentRead
    cleaned_characters: int
    chunk_count: int
    preview_chunks: list[str]


class KnowledgeEvaluationCase(BaseModel):
    query: str
    expected_document: str
    matched: bool
    top_score: float | None
    retrieved_documents: list[str]


class KnowledgeEvaluationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    total_cases: int
    hit_cases: int
    low_confidence_cases: int
    recall_at_3: float
    details: list[KnowledgeEvaluationCase]
    created_at: datetime


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    limit: int = Field(default=3, ge=1, le=10)
    category: str | None = Field(default=None, max_length=50)


class KnowledgeSearchResult(BaseModel):
    chunk_id: int
    document_id: int
    title: str
    category: str
    version: str
    content: str
    score: float
