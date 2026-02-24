import { usePolling } from '../hooks';
import { getOverview, formatBytes, shortId, timeAgo } from '../api';

export default function OverviewView() {
    const { data, loading, error } = usePolling(getOverview, 5000);

    if (loading) return <div className="loading"><div className="spinner" /> Loading overview…</div>;
    if (error) return <div className="loading" style={{ color: 'var(--accent-red)' }}>Error: {error}</div>;

    const d = data;
    const disk = d.disk || {};
    const replicaCount = Object.keys(d.replicas || {}).length;
    const activeCount = Object.values(d.active_downloads || {}).length;
    const domainCount = d.domain_count || 0;

    return (
        <div>
            <div className="page-header">
                <h2>Overview</h2>
                <p>Real-time snapshot of the image-download-service cluster</p>
            </div>

            {/* Top stats */}
            <div className="stats-grid">
                <div className="stat-card">
                    <div className="stat-label">Uptime</div>
                    <div className="stat-value cyan">{formatUptime(d.uptime_seconds)}</div>
                    <div className="stat-sub">Replica: {shortId(d.replica_id)}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Active Replicas</div>
                    <div className="stat-value green">{replicaCount}</div>
                    <div className="stat-sub">{activeCount} currently downloading</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Domains</div>
                    <div className="stat-value blue">{domainCount}</div>
                    <div className="stat-sub">with stored images</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Disk Used</div>
                    <div className="stat-value" style={{ color: diskColor(disk.used_percent) }}>
                        {formatBytes(disk.used_bytes)}
                    </div>
                    <div className="stat-sub">{disk.used_percent || 0}% of {formatBytes(disk.total_bytes)}</div>
                </div>
            </div>

            {/* Disk progress bar */}
            <div className="card" style={{ marginBottom: 'var(--space-xl)' }}>
                <div className="card-header">
                    <div className="card-title">Storage Usage</div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                        {formatBytes(disk.free_bytes)} free
                    </div>
                </div>
                <div className="progress-bar" style={{ height: 10 }}>
                    <div
                        className={`progress-fill ${diskColor(disk.used_percent) === 'var(--accent-green)' ? 'green' : diskColor(disk.used_percent) === 'var(--accent-yellow)' ? 'yellow' : 'red'}`}
                        style={{ width: `${disk.used_percent || 0}%` }}
                    />
                </div>
            </div>

            {/* Two-column: Replicas + Active Downloads */}
            <div className="data-grid">
                {/* Replicas */}
                <div className="card">
                    <div className="card-header">
                        <div className="card-title">Replica Status</div>
                        <span className="badge info">{replicaCount} online</span>
                    </div>
                    <div className="replica-grid">
                        {Object.entries(d.replicas || {}).map(([id, info]) => (
                            <div key={id} className={`replica-card ${info.state === 'processing' ? 'processing' : 'idle'}`}>
                                <div className="replica-name" title={id}>{shortId(id)}</div>
                                <div className="replica-status">
                                    {info.state === 'processing' ? '🔄' : '💤'}
                                </div>
                                <div className="replica-info">
                                    {info.state === 'processing'
                                        ? `${info.current_domain || '…'}`
                                        : timeAgo(info.last_seen)}
                                </div>
                            </div>
                        ))}
                        {replicaCount === 0 && (
                            <div className="empty-state" style={{ gridColumn: '1 / -1' }}>
                                <div className="empty-state-icon">🖥️</div>
                                <p>No replicas reporting yet</p>
                            </div>
                        )}
                    </div>
                </div>

                {/* Active Downloads */}
                <div className="card">
                    <div className="card-header">
                        <div className="card-title">Active Downloads</div>
                        <span className="badge success">{activeCount} in progress</span>
                    </div>
                    {activeCount > 0 ? (
                        <div className="table-wrapper">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Replica</th>
                                        <th>Domain</th>
                                        <th>Product</th>
                                        <th>Started</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {Object.entries(d.active_downloads || {}).map(([rid, dl]) => (
                                        <tr key={rid}>
                                            <td><code>{shortId(rid)}</code></td>
                                            <td>{dl.domain}</td>
                                            <td>{dl.product_id}</td>
                                            <td>{timeAgo(dl.started_at)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    ) : (
                        <div className="empty-state">
                            <div className="empty-state-icon">⏸️</div>
                            <p>No downloads in progress</p>
                        </div>
                    )}
                </div>
            </div>

            {/* Domain Summary */}
            {(d.domains || []).length > 0 && (
                <div className="card">
                    <div className="card-header">
                        <div className="card-title">Domain Summary</div>
                        <span className="badge info">{domainCount} domains</span>
                    </div>
                    <div className="table-wrapper">
                        <table>
                            <thead>
                                <tr>
                                    <th>Domain</th>
                                    <th>Products</th>
                                    <th>Synced</th>
                                    <th>Pending</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                {(d.domains || []).slice(0, 20).map((dom, i) => (
                                    <tr key={i}>
                                        <td style={{ fontWeight: 500, color: 'var(--text-primary)' }}>{dom.domain}</td>
                                        <td>{dom.total_products || 0}</td>
                                        <td>{dom.synced_products || 0}</td>
                                        <td>{dom.unsynced_products || 0}</td>
                                        <td>
                                            {dom.unsynced_products > 0
                                                ? <span className="badge warning">Pending</span>
                                                : <span className="badge success">Synced</span>}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    );
}

function formatUptime(seconds) {
    if (!seconds) return '0s';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
}

function diskColor(percent) {
    if (!percent) return 'var(--accent-green)';
    if (percent > 90) return 'var(--accent-red)';
    if (percent > 70) return 'var(--accent-yellow)';
    return 'var(--accent-green)';
}
