import axios from 'axios'
import type { KnowledgeReindexResult, Ticket } from './types'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api',
  timeout: 10_000,
})

export async function listTickets(): Promise<Ticket[]> {
  const { data } = await api.get<Ticket[]>('/tickets')
  return data
}

export async function getTicket(id: number): Promise<Ticket> {
  const { data } = await api.get<Ticket>(`/tickets/${id}`)
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

export async function reindexKnowledge(): Promise<KnowledgeReindexResult> {
  const { data } = await api.post<KnowledgeReindexResult>('/knowledge/reindex')
  return data
}
