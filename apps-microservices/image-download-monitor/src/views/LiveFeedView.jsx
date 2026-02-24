import { useSSE } from '../hooks';
import { shortId } from '../api';

const ACTION_STYLES = {
    image_complete: 'download',
    product_complete: 'download',
    product_start: 'info',
    http_error: 'error',
    download_failed: 'error',
    processing_error: 'error',
    dlq_permanent: 'error',
    dlq_exhausted: 'error',
    retry: 'skip',
};

export default function LiveFeedView() {
    const { events, connected, clear } = useSSE(500);

    // Separate downloads and errors
    const downloads = events.filter(e => e.type === 'download');
    const errors = events.filter(e => e.type === 'error');

    return (
        <div>
            <div className="page-header">
                <h2>Live Feed</h2>
                <p>
                    Real-time event stream via SSE —
                    <span className={`dot ${connected ? 'green' : 'red'}`} style={{ marginLeft: 8, marginRight: 4 }} />
                    {connected ? 'Connected' : 'Disconnected'}
                    <button onClick={clear} style={{
                        marginLeft: 16, background: 'var(--bg-input)', border: '1px solid var(--border-color)',
                        padding: '4px 12px', borderRadius: 'var(--radius-sm)', color: 'var(--text-secondary)',
                        cursor: 'pointer', fontSize: 12,
                    }}>Clear</button>
                </p>
            </div>

            {/* Stats bar */}
            <div className="stats-grid" style={{ marginBottom: 'var(--space-lg)' }}>
                <div className="stat-card">
                    <div className="stat-label">Total Events</div>
                    <div className="stat-value blue">{events.length}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Downloads</div>
                    <div className="stat-value green">{downloads.length}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Errors</div>
                    <div className="stat-value red">{errors.length}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Events/Min</div>
                    <div className="stat-value cyan">{estimateRate(events)}</div>
                </div>
            </div>

            {/* Event Feed */}
            <div className="card">
                <div className="card-header">
                    <div className="card-title">Event Stream</div>
                    <span className="badge info">{events.length} events</span>
                </div>
                <div className="event-feed">
                    {events.length === 0 && (
                        <div className="empty-state">
                            <div className="empty-state-icon">⚡</div>
                            <p>Waiting for events…</p>
                        </div>
                    )}
                    {[...events].reverse().map((evt, i) => (
                        <div className="event-item" key={i}>
                            <span className="event-time">
                                {evt.timestamp ? new Date(evt.timestamp).toLocaleTimeString() : '—'}
                            </span>
                            <span className={`event-action ${ACTION_STYLES[evt.action] || 'info'}`}>
                                {evt.action || evt.type}
                            </span>
                            <span className="event-details">
                                {formatEvent(evt)}
                            </span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

function formatEvent(evt) {
    const parts = [];
    if (evt.replica_id) parts.push(`replica:${shortId(evt.replica_id)}`);
    if (evt.domain) parts.push(`domain:${evt.domain}`);
    if (evt.product_id) parts.push(`product:${evt.product_id}`);
    if (evt.url) parts.push(evt.url.length > 60 ? evt.url.slice(0, 60) + '…' : evt.url);
    if (evt.status_code) parts.push(`HTTP ${evt.status_code}`);
    if (evt.error) parts.push(evt.error.length > 80 ? evt.error.slice(0, 80) + '…' : evt.error);
    if (evt.size_bytes) parts.push(`${(+evt.size_bytes / 1024).toFixed(0)}KB`);
    if (evt.duration_ms) parts.push(`${evt.duration_ms}ms`);
    if (evt.retry_count) parts.push(`retry ${evt.retry_count}/${evt.max_retries || '?'}`);
    return parts.join(' · ');
}

function estimateRate(events) {
    if (events.length < 2) return 0;
    const last = new Date(events[events.length - 1].timestamp).getTime();
    const first = new Date(events[0].timestamp).getTime();
    const diffMin = (last - first) / 60000;
    if (diffMin <= 0) return events.length;
    return Math.round(events.length / diffMin);
}
