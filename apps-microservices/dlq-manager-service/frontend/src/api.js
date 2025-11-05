import axios from 'axios';

const api = axios.create({
    baseURL: '/api', // Proxied by React dev server, and served by FastAPI in production
});

// Functionality #1: Dashboard
export const apiGetDashboardStats = (filters) => api.post('/dashboard-stats', filters);

// Functionality #2 & #8: Search (Lightweight)
export const apiSearchMessages = (searchParams) => api.post('/messages/search', searchParams);
export const apiSearchGroupedMessages = (searchParams) => api.post('/messages/grouped-search', searchParams);

// NEW: Endpoint to get full message details (Heavy)
export const apiGetMessageDetails = (messageId) => api.get(`/messages/${messageId}`);

// Functionality #4: Single Re-queue
export const apiRequeueMessage = (messageId) => api.post(`/messages/${messageId}/requeue`);

// Functionality #5: Bulk Actions
export const apiBulkRequeue = (data) => api.post('/messages/bulk-requeue', data);
export const apiBulkArchive = (data) => api.post('/messages/bulk-archive', data);

// Functionality #6: Re-queue by Filter
export const apiRequeueByFilter = (data) => api.post('/messages/requeue-by-filter', data);

// Functionality #7: Edit & Re-queue
export const apiEditAndRequeueMessage = (messageId, data) => api.put(`/messages/${messageId}/edit-and-requeue`, data);

// Functionality #9: History
export const apiGetHistory = (params) => api.get('/history', { params });