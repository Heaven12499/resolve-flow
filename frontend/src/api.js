import axios from 'axios';
const api = axios.create({
    baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api',
    timeout: 10_000,
});
export async function listTickets() {
    const { data } = await api.get('/tickets');
    return data;
}
export async function getTicket(id) {
    const { data } = await api.get(`/tickets/${id}`);
    return data;
}
export async function createTicket(orderNo, content) {
    const { data } = await api.post('/tickets', {
        order_no: orderNo,
        content,
    });
    return data;
}
export async function processTicket(id) {
    const { data } = await api.post(`/tickets/${id}/process`);
    return data;
}
export async function approveCoupon(id) {
    const { data } = await api.post(`/tickets/${id}/approve-coupon`);
    return data;
}
export async function reindexKnowledge() {
    const { data } = await api.post('/knowledge/reindex');
    return data;
}
