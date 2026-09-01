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

export interface KnowledgeCitation {
  document_id: number
  title: string
  version: string
  score: number
}

export interface AgentRun {
  id: number
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
  status: string
  created_at: string
  updated_at: string
  messages?: TicketMessage[]
  audit_logs?: AuditLog[]
  approval_tasks?: ApprovalTask[]
  agent_runs?: AgentRun[]
}
