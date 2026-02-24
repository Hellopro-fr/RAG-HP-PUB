import { Routes, Route, NavLink, Navigate } from 'react-router-dom';
import OverviewView from './views/OverviewView';
import LiveFeedView from './views/LiveFeedView';
import ReplicasView from './views/ReplicasView';
import DomainsView from './views/DomainsView';
import StorageView from './views/StorageView';
import ErrorsView from './views/ErrorsView';
import ProxyView from './views/ProxyView';

export default function App() {
    return (
        <div className="app-layout">
            {/* ---- Sidebar ---- */}
            <aside className="sidebar">
                <div className="sidebar-header">
                    <div className="sidebar-logo">
                        <div className="sidebar-logo-icon">📷</div>
                        <h1>
                            IDS Monitor
                            <span>image-download-service</span>
                        </h1>
                    </div>
                </div>

                <nav className="sidebar-nav">
                    <div className="nav-section">
                        <div className="nav-section-label">Dashboard</div>
                        <NavLink to="/overview" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                            <span className="nav-link-icon">📊</span>
                            <span>Overview</span>
                        </NavLink>
                        <NavLink to="/live" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                            <span className="nav-link-icon">⚡</span>
                            <span>Live Feed</span>
                        </NavLink>
                    </div>

                    <div className="nav-section">
                        <div className="nav-section-label">Infrastructure</div>
                        <NavLink to="/replicas" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                            <span className="nav-link-icon">🖥️</span>
                            <span>Replicas</span>
                        </NavLink>
                        <NavLink to="/storage" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                            <span className="nav-link-icon">💾</span>
                            <span>Storage</span>
                        </NavLink>
                        <NavLink to="/proxy" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                            <span className="nav-link-icon">🌐</span>
                            <span>Proxy</span>
                        </NavLink>
                    </div>

                    <div className="nav-section">
                        <div className="nav-section-label">Data</div>
                        <NavLink to="/domains" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                            <span className="nav-link-icon">🏷️</span>
                            <span>Domains</span>
                        </NavLink>
                        <NavLink to="/errors" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                            <span className="nav-link-icon">🚨</span>
                            <span>Errors</span>
                        </NavLink>
                    </div>
                </nav>

                <div className="sidebar-footer">
                    <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                        v1.0.0 — Real-time monitor
                    </div>
                </div>
            </aside>

            {/* ---- Main ---- */}
            <main className="main-content">
                <Routes>
                    <Route path="/" element={<Navigate to="/overview" replace />} />
                    <Route path="/overview" element={<OverviewView />} />
                    <Route path="/live" element={<LiveFeedView />} />
                    <Route path="/replicas" element={<ReplicasView />} />
                    <Route path="/domains" element={<DomainsView />} />
                    <Route path="/storage" element={<StorageView />} />
                    <Route path="/errors" element={<ErrorsView />} />
                    <Route path="/proxy" element={<ProxyView />} />
                </Routes>
            </main>
        </div>
    );
}
