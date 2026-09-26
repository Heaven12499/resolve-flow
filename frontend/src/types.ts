export interface TicketMessage {
  id: number
  sender_type: 'customer' | 'assistant' | 'agent'
  content: string
  created_at: string
}

export interface AuditLog {
  id: number
  action: string
  operator_type: string
  input_data: Record<string, unknown> | null
  output_data: Record<string, unknown> | null
  created_at: string
}

export interface ApprovalTask {
  id: number
  task_type: string
  status: string
  proposed_data: Record<string, unknown>
  decision_data: Record<string, unknown> | null
  created_at: string
  decided_at: string | null
}

export interface ApprovalQueueItem extends ApprovalTask {
  ticket_id: number
  ticket_no: string
  ticket_title: string
  ticket_content: string
  ticket_status: string
  risk_level: string
}

export interface KnowledgeReindexResult {
  document_count: number
  chunk_count: number
  collection_name: string
}

export interface KnowledgeDocument {
  id: number
  title: string
  content: string
  category: string
  version: string
  is_active: boolean
  source_name: string | null
  source_type: string
  source_metadata: Record<string, unknown> | null
  content_hash: string | null
  ingestion_status: string
  created_at: string
  updated_at: string
}

export interface KnowledgeIngestionResult {
  document: KnowledgeDocument
  cleaned_characters: number
  chunk_count: number
  preview_chunks: string[]
}

export interface KnowledgeDocumentPayload {
  title: string
  content: string
  category: string
  version: string
  is_active: boolean
}

export interface KnowledgeCitation {
  document_id: number
  title: string
  version: string
  category: string
  score: number
}

export interface AgentRun {
  id?: number
  sequence: number
  agent_name: string
  status: string
  provider: string
  model: string | null
  input_data: Record<string, unknown> | null
  output_data: Record<string, unknown> | null
  error: string | null
  duration_ms: number
  started_at: string
  finished_at: string | null
}

export interface AgentRunQueueItem extends AgentRun {
  ticket_id: number
  ticket_no: string
  ticket_title: string
  ticket_status: string
}

export interface CaseAgentState {
  status: string
  goal: string
  state_data: Record<string, unknown>
  pending_question: string | null
  created_at: string
  updated_at: string
}

export interface EvidenceAttachmentPayload {
  file_name: string
  media_type: 'image/jpeg' | 'image/png' | 'video/mp4' | 'application/pdf'
  storage_uri: string
  sha256: string
}

export interface EvidenceAttachment extends EvidenceAttachmentPayload {
  id: number
  order_id: number | null
  message_id: number | null
  uploaded_by: string
  created_at: string
}

export interface Ticket {
  id: number
  ticket_no: string
  customer_id: number
  order_id: number | null
  title: string
  content: string
  intent: string | null
  priority: string
  risk_level: string
  decision_source: string | null
  status: string
  created_at: string
  updated_at: string
  messages?: TicketMessage[]
  audit_logs?: AuditLog[]
  approval_tasks?: ApprovalTask[]
  agent_runs?: AgentRun[]
  case_agent_state?: CaseAgentState | null
  evidence_items?: EvidenceAttachment[]
}
