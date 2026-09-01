import axios from 'axios'
import type { AgentRunQueueItem, ApprovalQueueItem, KnowledgeDocument, KnowledgeDocumentPayload, KnowledgeEvaluationRun, KnowledgeIngestionResult, KnowledgeReindexResult, Ticket } from './types'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api',
  timeout: 35_000,
})

export async function listTickets(): Promise<Ticket[]> {
  const { data } = await api.get<Ticket[]>('/tickets')
  return data
}

export async function getTicket(id: number): Promise<Ticket> {
  const { data } = await api.get<Ticket>(`/tickets/${id}`)
  return data
}

export async function listAgentRuns(): Promise<AgentRunQueueItem[]> {
  const { data } = await api.get<AgentRunQueueItem[]>('/agent-runs')
  return data
}

export async function createTicket(orderNo: string, content: string): Promise<Ticket> {
  const { data } = await api.post<Ticket>('/tickets', {
    order_no: orderNo,
    content,
  })
  return data
}

export async function processTicket(id: number): Promise<Ticket> {
  const { data } = await api.post<Ticket>(`/tickets/${id}/process`)
  return data
}

export async function approveCoupon(id: number): Promise<Ticket> {
  const { data } = await api.post<Ticket>(`/tickets/${id}/approve-coupon`)
  return data
}

export async function listApprovals(): Promise<ApprovalQueueItem[]> {
  const { data } = await api.get<ApprovalQueueItem[]>('/approvals')
  return data
}

export async function approveCouponFromWorkbench(taskId: number): Promise<Ticket> {
  const { data } = await api.post<Ticket>(`/approvals/${taskId}/approve-coupon`)
  return data
}

export async function rejectApproval(taskId: number, reason: string): Promise<Ticket> {
  const { data } = await api.post<Ticket>(`/approvals/${taskId}/reject`, { reason })
  return data
}

export async function assignSupervisor(taskId: number, reason: string): Promise<Ticket> {
  const { data } = await api.post<Ticket>(`/approvals/${taskId}/assign-supervisor`, { reason })
  return data
}

export async function reindexKnowledge(): Promise<KnowledgeReindexResult> {
  const { data } = await api.post<KnowledgeReindexResult>('/knowledge/reindex')
  return data
}

export async function listKnowledgeDocuments(): Promise<KnowledgeDocument[]> {
  const { data } = await api.get<KnowledgeDocument[]>('/knowledge/documents')
  return data
}

export async function createKnowledgeDocument(payload: KnowledgeDocumentPayload): Promise<KnowledgeDocument> {
  const { data } = await api.post<KnowledgeDocument>('/knowledge/documents', payload)
  return data
}

export async function updateKnowledgeDocument(id: number, payload: Partial<KnowledgeDocumentPayload>): Promise<KnowledgeDocument> {
  const { data } = await api.patch<KnowledgeDocument>(`/knowledge/documents/${id}`, payload)
  return data
}

export async function ingestKnowledgeDocument(
  file: File,
  category: string,
  version = 'v1.0',
): Promise<KnowledgeIngestionResult> {
  const form = new FormData()
  form.append('file', file)
  form.append('category', category)
  form.append('version', version)
  const { data } = await api.post<KnowledgeIngestionResult>('/knowledge/documents/ingest', form)
  return data
}

export async function runKnowledgeEvaluation(): Promise<KnowledgeEvaluationRun> {
  const { data } = await api.post<KnowledgeEvaluationRun>('/knowledge/evaluations')
  return data
}

export async function listKnowledgeEvaluations(): Promise<KnowledgeEvaluationRun[]> {
  const { data } = await api.get<KnowledgeEvaluationRun[]>('/knowledge/evaluations')
  return data
}
