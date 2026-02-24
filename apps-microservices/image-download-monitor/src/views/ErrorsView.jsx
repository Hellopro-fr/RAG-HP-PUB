import { usePolling } from '../hooks';
import { getErrors, shortId } from '../api';

export default function ErrorsView() {
    const { data, loading, error } = usePolling(getErrors, 5000);

    if (loading) return <div className="loading"><div className="spinner" /> Loading errors…</div>;
    if (error) return <div className="loading" style={{ color: 'var(--accent-red)' }}>Error: {error}</div>;

    const errors = data.errors || [];

    // Categorize errors
    const httpErrors = errors.filter(e => e.action === 'http_error');
    const dlqErrors = errors.filter(e => e.action?.startsWith('dlq_'));
    const dlErrors = errors.filter(e => e.action === 'download_failed');
    const procErrors = errors.filter(e => e.action === 'processing_error');
    const retries = errors.filter(e => e.action === 'retry');

    // HTTP status code breakdown
    const statusCounts = {};
    httpErrors.forEach(e => {
        const code = e.status_code || 'unknown';
        statusCounts[code] = (statusCounts[code] || 0) + 1;
    });

    // Domain error breakdown
    const domainCounts = {};
    errors.forEach(e => {
        if (e.domain) {
            domainCounts[e.domain] = (domainCounts[e.domain] || 0) + 1;
        }
    });
    const domainList = Object.entries(domainCounts).sort((a, b) => b[1] - a[1]);

    return (
        <div>
            <div className="page-header">
                <h2>Errors</h2>
                <p>Download errors, HTTP failures, DLQ events, and retries</p>
            </div>

            <div className="stats-grid">
                <div className="stat-card">
                    <div className="stat-label">Total Errors</div>
                    <div className="stat-value red">{errors.length}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">HTTP Errors</div>
                    <div className="stat-value yellow">{httpErrors.length}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">DLQ</div>
                    <div className="stat-value" style={{ color: 'var(--accent-orange)' }}>{dlqErrors.length}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Download Failures</div>
                    <div className="stat-value red">{dlErrors.length}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Processing Errors</div>
                    <div className="stat-value purple">{procErrors.length}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Retries</div>
                    <div className="stat-value cyan">{retries.length}</div>
                </div>
            </div>

            <div className="data-grid">
                {/* HTTP Status Breakdown */}
                <div className="card">
                    <div className="card-header">
                        <div className="card-title">HTTP Status Codes</div>
                    </div>
                    {Object.keys(statusCounts).length > 0 ? (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-md)' }}>
                            {Object.entries(statusCounts).sort((a, b) => b[1] - a[1]).map(([code, count]) => (
                                <div key={code} style={{
                                    padding: 'var(--space-md)',
                                    background: 'var(--bg-input)',
                                    borderRadius: 'var(--radius-md)',
                                    textAlign: 'center',
                                    minWidth: 80,
                                }}>
                                    <div style={{ fontSize: 24, fontWeight: 700, color: statusColor(code) }}>{count}</div>
                                    <div style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                                        HTTP {code}
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="empty-state">
                            <div className="empty-state-icon">✅</div>
                            <p>No HTTP errors</p>
                        </div>
                    )}
                </div>

                {/* Errors by Domain */}
                <div className="card">
                    <div className="card-header">
                        <div className="card-title">Errors by Domain</div>
                    </div>
                    {domainList.length > 0 ? (
                        <div className="table-wrapper" style={{ maxHeight: 300, overflowY: 'auto' }}>
                            <table>
                                <thead>
                                    <tr><th>Domain</th><th>Errors</th><th>Share</th></tr>
                                </thead>
                                <tbody>
                                    {domainList.slice(0, 15).map(([dom, cnt]) => (
                                        <tr key={dom}>
                                            <td style={{ fontWeight: 500 }}>{dom}</td>
                                            <td style={{ color: 'var(--accent-red)' }}>{cnt}</td>
                                            <td>
                                                <div className="progress-bar" style={{ width: 100, height: 4 }}>
                                                    <div className="progress-fill red" style={{ width: `${(cnt / errors.length) * 100}%` }} />
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    ) : (
                        <div className="empty-state">
                            <div className="empty-state-icon">✅</div>
                            <p>No domain errors</p>
                        </div>
                    )}
                </div>
            </div>

            {/* Error Log */}
            <div className="card">
                <div className="card-header">
                    <div className="card-title">Recent Errors</div>
                    <span className="badge error">{errors.length} events</span>
                </div>
                <div className="event-feed">
                    {errors.length === 0 && (
                        <div className="empty-state">
                            <div className="empty-state-icon">✅</div>
                            <p>No recent errors — all clear!</p>
                        </div>
                    )}
                    {[...errors].reverse().slice(0, 100).map((evt, i) => (
                        <div className="event-item" key={i}>
                            <span className="event-time">
                                {evt.timestamp ? new Date(evt.timestamp).toLocaleTimeString() : '—'}
                            </span>
                            <span className="event-action error">{evt.action}</span>
                            <span className="event-details">
                                {[
                                    evt.replica_id && `replica:${shortId(evt.replica_id)}`,
                                    evt.domain && `domain:${evt.domain}`,
                                    evt.product_id && `product:${evt.product_id}`,
                                    evt.status_code && `HTTP ${evt.status_code}`,
                                    evt.error && (evt.error.length > 100 ? evt.error.slice(0, 100) + '…' : evt.error),
                                ].filter(Boolean).join(' · ')}
                            </span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

function statusColor(code) {
    const c = parseInt(code);
    if (c >= 500) return 'var(--accent-red)';
    if (c >= 400) return 'var(--accent-yellow)';
    if (c >= 300) return 'var(--accent-blue)';
    return 'var(--text-muted)';
}
