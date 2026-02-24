import { usePolling } from '../hooks';
import { getDisk, formatBytes } from '../api';

const COLORS = [
    '#6366f1', '#22d3ee', '#10b981', '#f59e0b', '#a855f7',
    '#f97316', '#ec4899', '#14b8a6', '#8b5cf6', '#ef4444',
];

export default function StorageView() {
    const { data, loading, error } = usePolling(getDisk, 15000);

    if (loading) return <div className="loading"><div className="spinner" /> Loading storage…</div>;
    if (error) return <div className="loading" style={{ color: 'var(--accent-red)' }}>Error: {error}</div>;

    const disk = data.disk || {};
    const domains = data.domains || [];
    const usedPct = disk.used_percent || 0;

    // Top 10 domains for chart
    const topDomains = domains.slice(0, 10);
    const otherSize = domains.slice(10).reduce((s, d) => s + d.size_bytes, 0);
    const chartData = [...topDomains];
    if (otherSize > 0) chartData.push({ domain: 'Others', size_bytes: otherSize, file_count: 0 });
    const totalDomainSize = chartData.reduce((s, d) => s + d.size_bytes, 0);

    return (
        <div>
            <div className="page-header">
                <h2>Storage</h2>
                <p>Disk usage analysis and per-domain breakdown</p>
            </div>

            <div className="stats-grid">
                <div className="stat-card">
                    <div className="stat-label">Total</div>
                    <div className="stat-value blue">{formatBytes(disk.total_bytes)}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Used</div>
                    <div className="stat-value" style={{ color: usedPct > 90 ? 'var(--accent-red)' : usedPct > 70 ? 'var(--accent-yellow)' : 'var(--accent-green)' }}>
                        {formatBytes(disk.used_bytes)}
                    </div>
                    <div className="stat-sub">{usedPct}%</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Free</div>
                    <div className="stat-value green">{formatBytes(disk.free_bytes)}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Archives</div>
                    <div className="stat-value purple">{formatBytes(disk.archives_size_bytes)}</div>
                    <div className="stat-sub">{disk.archives_count || 0} files</div>
                </div>
            </div>

            {/* Main progress bar */}
            <div className="card" style={{ marginBottom: 'var(--space-xl)' }}>
                <div className="card-header">
                    <div className="card-title">Overall Disk Usage</div>
                    <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{usedPct}%</span>
                </div>
                <div className="progress-bar" style={{ height: 12 }}>
                    <div
                        className={`progress-fill ${usedPct > 90 ? 'red' : usedPct > 70 ? 'yellow' : 'green'}`}
                        style={{ width: `${usedPct}%` }}
                    />
                </div>
            </div>

            <div className="data-grid">
                {/* Donut Chart */}
                <div className="card">
                    <div className="card-header">
                        <div className="card-title">Usage by Domain (Top 10)</div>
                    </div>
                    {chartData.length > 0 ? (
                        <div className="donut-container">
                            <svg className="donut-svg" viewBox="0 0 42 42">
                                <circle cx="21" cy="21" r="15.915" fill="none" stroke="var(--bg-input)" strokeWidth="3" />
                                {renderDonut(chartData, totalDomainSize)}
                            </svg>
                            <div className="donut-legend">
                                {chartData.map((d, i) => (
                                    <div key={i} className="donut-legend-item">
                                        <div className="donut-legend-color" style={{ background: COLORS[i % COLORS.length] }} />
                                        <span style={{ flex: 1 }}>{d.domain}</span>
                                        <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>{formatBytes(d.size_bytes)}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    ) : (
                        <div className="empty-state">
                            <div className="empty-state-icon">📊</div>
                            <p>No domain data</p>
                        </div>
                    )}
                </div>

                {/* Domain table */}
                <div className="card">
                    <div className="card-header">
                        <div className="card-title">All Domains ({domains.length})</div>
                    </div>
                    <div className="table-wrapper" style={{ maxHeight: 400, overflowY: 'auto' }}>
                        <table>
                            <thead>
                                <tr>
                                    <th>Domain</th>
                                    <th>Size</th>
                                    <th>Files</th>
                                    <th>Share</th>
                                </tr>
                            </thead>
                            <tbody>
                                {domains.map((d, i) => {
                                    const share = totalDomainSize > 0 ? ((d.size_bytes / totalDomainSize) * 100).toFixed(1) : 0;
                                    return (
                                        <tr key={i}>
                                            <td style={{ fontWeight: 500, color: 'var(--text-primary)' }}>{d.domain}</td>
                                            <td>{formatBytes(d.size_bytes)}</td>
                                            <td>{(d.file_count || 0).toLocaleString()}</td>
                                            <td>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                                    <div className="progress-bar" style={{ flex: 1, height: 4 }}>
                                                        <div className="progress-fill" style={{ width: `${share}%` }} />
                                                    </div>
                                                    <span style={{ fontSize: 11, color: 'var(--text-muted)', width: 40 }}>{share}%</span>
                                                </div>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    );
}

function renderDonut(data, total) {
    if (!total) return null;
    const circumference = 2 * Math.PI * 15.915;
    let offset = 0;

    return data.map((d, i) => {
        const pct = d.size_bytes / total;
        const dash = pct * circumference;
        const gap = circumference - dash;
        const el = (
            <circle
                key={i}
                cx="21" cy="21" r="15.915"
                fill="none"
                stroke={COLORS[i % COLORS.length]}
                strokeWidth="3"
                strokeDasharray={`${dash} ${gap}`}
                strokeDashoffset={-offset}
                style={{ transition: 'all 0.5s ease' }}
            />
        );
        offset += dash;
        return el;
    });
}
