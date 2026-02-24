import { usePolling } from '../hooks';
import { getDomains, formatBytes } from '../api';

export default function DomainsView() {
    const { data, loading, error } = usePolling(getDomains, 10000);

    if (loading) return <div className="loading"><div className="spinner" /> Loading domains…</div>;
    if (error) return <div className="loading" style={{ color: 'var(--accent-red)' }}>Error: {error}</div>;

    const domains = data.domains || [];
    const totalProducts = domains.reduce((s, d) => s + (d.total_products || 0), 0);
    const totalUnsynced = domains.reduce((s, d) => s + (d.unsynced_products || 0), 0);
    const totalDiskUsage = domains.reduce((s, d) => s + (d.disk_usage_bytes || 0), 0);
    const totalFiles = domains.reduce((s, d) => s + (d.file_count || 0), 0);

    return (
        <div>
            <div className="page-header">
                <h2>Domains</h2>
                <p>Image storage breakdown by domain</p>
            </div>

            <div className="stats-grid">
                <div className="stat-card">
                    <div className="stat-label">Total Domains</div>
                    <div className="stat-value blue">{domains.length}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Total Products</div>
                    <div className="stat-value green">{totalProducts.toLocaleString()}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Pending Sync</div>
                    <div className="stat-value yellow">{totalUnsynced.toLocaleString()}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Total Size</div>
                    <div className="stat-value cyan">{formatBytes(totalDiskUsage)}</div>
                    <div className="stat-sub">{totalFiles.toLocaleString()} files</div>
                </div>
            </div>

            <div className="card">
                <div className="card-header">
                    <div className="card-title">All Domains</div>
                    <span className="badge info">{domains.length}</span>
                </div>
                <div className="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Domain</th>
                                <th>Products</th>
                                <th>Synced</th>
                                <th>Pending</th>
                                <th>Files</th>
                                <th>Disk</th>
                                <th>Sync Status</th>
                                <th>Last Updated</th>
                            </tr>
                        </thead>
                        <tbody>
                            {domains.map((dom, i) => {
                                const syncPct = dom.total_products > 0
                                    ? Math.round((dom.synced_products / dom.total_products) * 100)
                                    : 0;
                                return (
                                    <tr key={i}>
                                        <td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{dom.domain}</td>
                                        <td>{dom.total_products || 0}</td>
                                        <td>{dom.synced_products || 0}</td>
                                        <td>
                                            {dom.unsynced_products > 0
                                                ? <span style={{ color: 'var(--accent-yellow)', fontWeight: 600 }}>{dom.unsynced_products}</span>
                                                : '0'}
                                        </td>
                                        <td>{(dom.file_count || 0).toLocaleString()}</td>
                                        <td>{formatBytes(dom.disk_usage_bytes || 0)}</td>
                                        <td>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                                <div className="progress-bar" style={{ flex: 1, height: 4 }}>
                                                    <div
                                                        className={`progress-fill ${syncPct === 100 ? 'green' : syncPct > 50 ? '' : 'yellow'}`}
                                                        style={{ width: `${syncPct}%` }}
                                                    />
                                                </div>
                                                <span style={{ fontSize: 11, color: 'var(--text-muted)', width: 36 }}>{syncPct}%</span>
                                            </div>
                                        </td>
                                        <td style={{ fontSize: 11, color: 'var(--text-muted)' }}>{dom.last_updated || '—'}</td>
                                    </tr>
                                );
                            })}
                            {domains.length === 0 && (
                                <tr>
                                    <td colSpan={8}>
                                        <div className="empty-state">
                                            <div className="empty-state-icon">🏷️</div>
                                            <p>No domains found</p>
                                        </div>
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
