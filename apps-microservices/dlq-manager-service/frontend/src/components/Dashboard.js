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

    if (loading) return <div className="text-center p-8">Loading dashboard...</div>;
    if (error) return <div className="bg-rouge-light text-rouge-primary p-4 rounded-md">{error}</div>;
    if (!stats) return <div className="text-center p-8">No data available.</div>;

    const serviceData = stats.by_service.map(item => ({ name: item.key, count: item.doc_count }));
    const timeData = stats.over_time.map(item => ({ time: new Date(item.key).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}), count: item.doc_count }));

    return (
        <div className="space-y-8">
            <h2 className="text-3xl font-bold text-white-primary">DLQ Health Overview</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-bleu-noir p-6 rounded-lg shadow-lg border border-gris-primary/20">
                    <h3 className="text-lg font-medium text-gris-clair">Pending Messages (New)</h3>
                    <p className="text-5xl font-bold text-orange-primary mt-2">{stats.pending_count}</p>
                </div>
                <div className="bg-bleu-noir p-6 rounded-lg shadow-lg border border-gris-primary/20">
                    <h3 className="text-lg font-medium text-gris-clair">Top Errors</h3>
                    <ul className="mt-2 space-y-1 text-sm">
                        {stats.by_error.map(e => <li key={e.key} className="flex justify-between"><span>{e.key}</span> <span>{e.doc_count}</span></li>)}
                    </ul>
                </div>
            </div>

            <div className="bg-bleu-noir p-6 rounded-lg shadow-lg border border-gris-primary/20">
                <h3 className="text-lg font-medium text-gris-clair mb-4">Failures by Service</h3>
                <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={serviceData} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
                        <XAxis dataKey="name" stroke="#5F5F5F" fontSize={12} />
                        <YAxis stroke="#5F5F5F" fontSize={12}/>
                        <Tooltip contentStyle={{ backgroundColor: '#041325', border: '1px solid #5F5F5F' }} />
                        <Legend wrapperStyle={{fontSize: "14px"}}/>
                        <Bar dataKey="count" fill="#FB5607" />
                    </BarChart>
                </ResponsiveContainer>
            </div>

            <div className="bg-bleu-noir p-6 rounded-lg shadow-lg border border-gris-primary/20">
                <h3 className="text-lg font-medium text-gris-clair mb-4">Failures Over Time (Last 24h)</h3>
                 <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={timeData} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
                        <XAxis dataKey="time" stroke="#5F5F5F" fontSize={12} />
                        <YAxis stroke="#5F5F5F" fontSize={12}/>
                        <Tooltip contentStyle={{ backgroundColor: '#041325', border: '1px solid #5F5F5F' }} />
                        <Legend wrapperStyle={{fontSize: "14px"}}/>
                        <Line type="monotone" dataKey="count" stroke="#02C39A" strokeWidth={2} dot={false} />
                    </LineChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
}

export default Dashboard;