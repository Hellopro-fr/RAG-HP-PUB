import React, { useState, useEffect } from 'react';
import { apiGetDashboardStats } from '../api';
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, LineChart, Line } from 'recharts';

function Dashboard() {
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        const fetchStats = async () => {
            try {
                setLoading(true);
                const response = await apiGetDashboardStats();
                setStats(response.data);
            } catch (err) {
                setError('Failed to load dashboard stats.');
                console.error(err);
            } finally {
                setLoading(false);
            }
        };
        fetchStats();
    }, []);

    if (loading) return <div>Loading dashboard...</div>;
    if (error) return <div className="error-message">{error}</div>;
    if (!stats) return <div>No data available.</div>;

    const serviceData = stats.by_service.map(item => ({ name: item.key, count: item.doc_count }));
    const timeData = stats.over_time.map(item => ({ time: new Date(item.key).toLocaleTimeString(), count: item.doc_count }));


    return (
        <div className="dashboard">
            <h2>DLQ Health Overview</h2>
            <div className="stats-grid">
                <div className="stat-card">
                    <h3>Total Failed Messages</h3>
                    <p>{stats.total_failed}</p>
                </div>
                <div className="stat-card">
                     <h3>Top Errors</h3>
                     <ul>
                        {stats.by_error.map(e => <li key={e.key}>{e.key} ({e.doc_count})</li>)}
                     </ul>
                </div>
            </div>

            <div className="chart-container">
                <h3>Failures by Service</h3>
                <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={serviceData}>
                        <XAxis dataKey="name" />
                        <YAxis />
                        <Tooltip />
                        <Legend />
                        <Bar dataKey="count" fill="#8884d8" />
                    </BarChart>
                </ResponsiveContainer>
            </div>

            <div className="chart-container">
                <h3>Failures Over Time (Last 24h)</h3>
                <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={timeData}>
                        <XAxis dataKey="time" />
                        <YAxis />
                        <Tooltip />
                        <Legend />
                        <Line type="monotone" dataKey="count" stroke="#82ca9d" />
                    </LineChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
}

export default Dashboard;