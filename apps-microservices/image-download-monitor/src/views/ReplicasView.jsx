import { usePolling } from '../hooks';
import { getReplicas, shortId, timeAgo } from '../api';

export default function ReplicasView() {
    const { data, loading, error } = usePolling(getReplicas, 3000);

    if (loading) return <div className="loading"><div className="spinner" /> Loading replicas…</div>;
    if (error) return <div className="loading" style={{ color: 'var(--accent-red)' }}>Error: {error}</div>;

    const replicas = data.replicas || {};
    const active = data.active_downloads || {};
    const ids = Object.keys(replicas);

    const processingCount = ids.filter(id => replicas[id].state === 'processing').length;
    const idleCount = ids.length - processingCount;

    return (
        <div>
            <div className="page-header">
                <h2>Replicas</h2>
                <p>Status of all {ids.length} replicas in the cluster (updates every 3s)</p>
            </div>

            {/* Stats */}
            <div className="stats-grid">
                <div className="stat-card">
                    <div className="stat-label">Total Replicas</div>
                    <div className="stat-value blue">{ids.length}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Processing</div>
                    <div className="stat-value green">{processingCount}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Idle</div>
                    <div className="stat-value" style={{ color: 'var(--text-muted)' }}>{idleCount}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Active Downloads</div>
                    <div className="stat-value cyan">{Object.keys(active).length}</div>
                </div>
            </div>

            {/* Replica Grid */}
            <div className="card" style={{ marginBottom: 'var(--space-xl)' }}>
                <div className="card-header">
                    <div className="card-title">Replica Grid</div>
                </div>
                <div className="replica-grid">
                    {ids.map(id => {
                        const info = replicas[id];
                        const dl = active[id];
                        return (
                            <div key={id} className={`replica-card ${info.state === 'processing' ? 'processing' : 'idle'}`}>
                                <div className="replica-name" title={id}>{shortId(id)}</div>
                                <div className="replica-status">
                                    {info.state === 'processing' ? '🔄' : '💤'}
                                </div>
                                <div className="replica-info">
                                    {info.state === 'processing' ? (
                                        <>
                                            <div>{info.current_domain || '—'}</div>
                                            <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                                                {info.current_product || ''}
                                            </div>
                                        </>
                                    ) : (
                                        <>
                                            <div>{timeAgo(info.last_seen)}</div>
                                            {info.last_domain && (
                                                <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                                                    Last: {info.last_domain}
                                                </div>
                                            )}
                                        </>
                                    )}
                                </div>
                            </div>
                        );
                    })}
                    {ids.length === 0 && (
                        <div className="empty-state" style={{ gridColumn: '1 / -1' }}>
                            <div className="empty-state-icon">🖥️</div>
                            <p>No replicas detected</p>
                        </div>
                    )}
                </div>
            </div>

            {/* Active Downloads Detail */}
            {Object.keys(active).length > 0 && (
                <div className="card">
                    <div className="card-header">
                        <div className="card-title">Active Downloads Detail</div>
                    </div>
                    <div className="table-wrapper">
                        <table>
                            <thead>
                                <tr>
                                    <th>Replica</th>
                                    <th>Domain</th>
                                    <th>Product</th>
                                    <th>URL</th>
                                    <th>Index</th>
                                    <th>Started</th>
                                </tr>
                            </thead>
                            <tbody>
                                {Object.entries(active).map(([rid, dl]) => (
                                    <tr key={rid}>
                                        <td><code>{shortId(rid)}</code></td>
                                        <td>{dl.domain}</td>
                                        <td>{dl.product_id}</td>
                                        <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                            {dl.url || '—'}
                                        </td>
                                        <td>{dl.index || '—'}</td>
                                        <td>{timeAgo(dl.started_at)}</td>
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
