/**
 * API client for image-download-service monitoring endpoints.
 * All calls go through the Vite proxy in dev, or directly in production.
 */

// In production (Docker), the API is on the same origin via nginx proxy
// In dev, Vite proxy handles /api -> http://localhost:8505
const BASE = import.meta.env.VITE_API_URL || '/api';

async function fetchJSON(path, opts = {}) {
    const res = await fetch(`${BASE}${path}`, opts);
    if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
    return res.json();
}

// --- Stats ---
export const getOverview = () => fetchJSON('/stats/overview');
export const getReplicas = () => fetchJSON('/stats/replicas');
export const getDomains = () => fetchJSON('/stats/domains');
export const getErrors = (count = 200) => fetchJSON(`/stats/errors?count=${count}`);
export const getEvents = (count = 200) => fetchJSON(`/stats/events?count=${count}`);
export const getDisk = () => fetchJSON('/stats/disk');

// --- Domains (archiver) ---
export const listDomains = () => fetchJSON('/domains');
export const getDomainStatus = (d) => fetchJSON(`/domains/${d}/status`);
export const getRecentDomains = (h = 6) => fetchJSON(`/domains/recent?hours=${h}`);

// --- Archives ---
export const listArchives = () => fetchJSON('/archives');

// --- Health ---
export const getHealth = () => fetchJSON('/health');

// --- SSE Stream ---
export function createEventStream(onEvent, onError) {
    const url = `${BASE}/events/stream`;
    const source = new EventSource(url);

    source.onmessage = (e) => {
        try {
            const data = JSON.parse(e.data);
            onEvent(data);
        } catch (err) {
            console.warn('SSE parse error:', err);
        }
    };

    source.onerror = (e) => {
        if (onError) onError(e);
    };

    return source; // caller must close()
}

// --- Helpers ---
export function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

export function formatDuration(ms) {
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${(ms / 60000).toFixed(1)}m`;
}

export function timeAgo(isoStr) {
    if (!isoStr) return '—';
    const diff = Date.now() - new Date(isoStr).getTime();
    const s = Math.floor(diff / 1000);
    if (s < 60) return `${s}s ago`;
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
}

export function shortId(id) {
    if (!id) return '—';
    return id.length > 12 ? id.slice(0, 12) : id;
}
