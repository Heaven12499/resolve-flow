import axios from 'axios'
import type { AgentRunQueueItem, ApprovalQueueItem, KnowledgeDocument, KnowledgeDocumentPayload, KnowledgeIngestionResult, KnowledgeReindexResult, Ticket } from './types'

const accessTokenKey = 'resolveflow_access_token'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api',
  timeout: 35_000,
})

api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem(accessTokenKey)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export interface ApiHealth {
  status: string
  auth_enabled: boolean
}

export interface LoginResult {
  access_token: string
  token_type: string
  expires_in: number
  username: string
  role: string
}

export async function getHealth(): Promise<ApiHealth> {
  const { data } = await api.get<ApiHealth>('/health')
  return data
}

export async function login(username: string, password: string): Promise<LoginResult> {
  const { data } = await api.post<LoginResult>('/auth/login', { username, password })
  sessionStorage.setItem(accessTokenKey, data.access_token)
  return data
}

export function hasAccessToken(): boolean {
  return Boolean(sessionStorage.getItem(accessTokenKey))
}

export function clearAccessToken(): void {
  sessionStorage.removeItem(accessTokenKey)
}

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
