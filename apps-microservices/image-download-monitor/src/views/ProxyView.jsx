import { usePolling, useSSE } from '../hooks';
import { getOverview, shortId } from '../api';

export default function ProxyView() {
    const { data, loading, error } = usePolling(getOverview, 5000);
    const { events } = useSSE(200);

    if (loading) return <div className="loading"><div className="spinner" /> Loading proxy data…</div>;
    if (error) return <div className="loading" style={{ color: 'var(--accent-red)' }}>Error: {error}</div>;

    // Extract proxy-related events
    const proxyErrors = events.filter(e => e.action === 'download_failed' || (e.error && e.error.toLowerCase().includes('proxy')));
    const httpErrors = events.filter(e => e.action === 'http_error');
    const downloads = events.filter(e => e.action === 'image_complete');
    const successRate = downloads.length > 0
        ? ((downloads.length / (downloads.length + httpErrors.length + proxyErrors.length)) * 100).toFixed(1)
        : 100;

    // Calculate total bandwidth from events
    const totalBytes = downloads.reduce((s, e) => s + (parseInt(e.size_bytes) || 0), 0);
    const avgLatency = downloads.length > 0
        ? Math.round(downloads.reduce((s, e) => s + (parseInt(e.duration_ms) || 0), 0) / downloads.length)
        : 0;

    return (
        <div>
            <div className="page-header">
                <h2>Proxy & Network</h2>
                <p>Download performance, bandwidth, and proxy health</p>
            </div>

            <div className="stats-grid">
                <div className="stat-card">
                    <div className="stat-label">Success Rate</div>
                    <div className="stat-value" style={{ color: parseFloat(successRate) > 95 ? 'var(--accent-green)' : parseFloat(successRate) > 80 ? 'var(--accent-yellow)' : 'var(--accent-red)' }}>
                        {successRate}%
                    </div>
                    <div className="stat-sub">from live events</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Downloads (live)</div>
                    <div className="stat-value green">{downloads.length}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">HTTP Errors (live)</div>
                    <div className="stat-value yellow">{httpErrors.length}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Failed (live)</div>
                    <div className="stat-value red">{proxyErrors.length}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Bandwidth (live)</div>
                    <div className="stat-value cyan">{formatBandwidth(totalBytes)}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Avg Latency</div>
                    <div className="stat-value purple">{avgLatency}ms</div>
                </div>
            </div>

            <div className="data-grid">
                {/* Bandwidth by Domain */}
                <div className="card">
                    <div className="card-header">
                        <div className="card-title">Bandwidth by Domain (live)</div>
                    </div>
                    {(() => {
                        const byDomain = {};
                        downloads.forEach(e => {
                            const d = e.domain || 'unknown';
                            byDomain[d] = (byDomain[d] || 0) + (parseInt(e.size_bytes) || 0);
                        });
                        const sorted = Object.entries(byDomain).sort((a, b) => b[1] - a[1]);
                        if (sorted.length === 0) {
                            return (
                                <div className="empty-state">
                                    <div className="empty-state-icon">🌐</div>
                                    <p>No download data yet</p>
                                </div>
                            );
                        }
                        return (
                            <div className="table-wrapper" style={{ maxHeight: 300, overflowY: 'auto' }}>
                                <table>
                                    <thead>
                                        <tr><th>Domain</th><th>Downloaded</th><th>Share</th></tr>
                                    </thead>
                                    <tbody>
                                        {sorted.map(([dom, bytes]) => (
                                            <tr key={dom}>
                                                <td style={{ fontWeight: 500 }}>{dom}</td>
                                                <td>{formatBandwidth(bytes)}</td>
                                                <td>
                                                    <div className="progress-bar" style={{ width: 80, height: 4 }}>
                                                        <div className="progress-fill" style={{ width: `${(bytes / totalBytes) * 100}%` }} />
                                                    </div>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        );
                    })()}
                </div>

                {/* Latency Distribution */}
                <div className="card">
                    <div className="card-header">
                        <div className="card-title">Latency Distribution (live)</div>
                    </div>
                    {(() => {
                        const buckets = { '<100ms': 0, '100-500ms': 0, '500ms-1s': 0, '1-3s': 0, '3-10s': 0, '>10s': 0 };
                        downloads.forEach(e => {
                            const ms = parseInt(e.duration_ms) || 0;
                            if (ms < 100) buckets['<100ms']++;
                            else if (ms < 500) buckets['100-500ms']++;
                            else if (ms < 1000) buckets['500ms-1s']++;
                            else if (ms < 3000) buckets['1-3s']++;
                            else if (ms < 10000) buckets['3-10s']++;
                            else buckets['>10s']++;
                        });

                        if (downloads.length === 0) {
                            return (
                                <div className="empty-state">
                                    <div className="empty-state-icon">⏱️</div>
                                    <p>No latency data yet</p>
                                </div>
                            );
                        }

                        const maxCount = Math.max(...Object.values(buckets));
                        return (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)' }}>
                                {Object.entries(buckets).map(([label, count]) => (
                                    <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)' }}>
                                        <span style={{ width: 80, fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', textAlign: 'right' }}>{label}</span>
                                        <div className="progress-bar" style={{ flex: 1, height: 16 }}>
                                            <div
                                                className="progress-fill"
                                                style={{
                                                    width: maxCount > 0 ? `${(count / maxCount) * 100}%` : '0%',
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    paddingLeft: 6,
                                                    fontSize: 10,
                                                    color: 'white',
                                                    fontWeight: 600,
                                                }}
                                            >
                                                {count > 0 && count}
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        );
                    })()}
                </div>
            </div>

            {/* Recent Downloads Feed */}
            <div className="card">
                <div className="card-header">
                    <div className="card-title">Recent Downloads</div>
                    <span className="badge success">{downloads.length} images</span>
                </div>
                <div className="event-feed">
                    {downloads.length === 0 && (
                        <div className="empty-state">
                            <div className="empty-state-icon">📷</div>
                            <p>No downloads observed yet</p>
                        </div>
                    )}
                    {[...downloads].reverse().slice(0, 50).map((evt, i) => (
                        <div className="event-item" key={i}>
                            <span className="event-time">
                                {evt.timestamp ? new Date(evt.timestamp).toLocaleTimeString() : '—'}
                            </span>
                            <span className="event-action download">✓ {evt.domain}</span>
                            <span className="event-details">
                                {[
                                    `product:${evt.product_id}`,
                                    evt.size_bytes && `${(parseInt(evt.size_bytes) / 1024).toFixed(0)}KB`,
                                    evt.duration_ms && `${evt.duration_ms}ms`,
                                    evt.replica_id && `replica:${shortId(evt.replica_id)}`,
                                ].filter(Boolean).join(' · ')}
                            </span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

function formatBandwidth(bytes) {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}
