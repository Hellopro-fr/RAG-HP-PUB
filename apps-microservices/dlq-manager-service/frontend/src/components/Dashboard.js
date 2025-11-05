import React, { useState, useEffect } from 'react';
import { apiGetDashboardStats } from '../api';
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, LineChart, Line } from 'recharts';

function Dashboard() {
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [filters, setFilters] = useState({ date_start: '', date_end: '' });

    const fetchStats = async () => {
        try {
            setLoading(true);
            const body = {};
            if (filters.date_start) body.date_start = filters.date_start;
            if (filters.date_end) body.date_end = filters.date_end;
            
            const response = await apiGetDashboardStats(body);
            setStats(response.data);
        } catch (err) {
            setError('Failed to load dashboard stats.');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };
    
    useEffect(() => {
        fetchStats();
    }, [filters]);

    const handleFilterChange = (e) => {
        setFilters(prev => ({...prev, [e.target.name]: e.target.value}));
    };

    if (loading && !stats) return <div className="text-center p-8">Loading dashboard...</div>;
    if (error) return <div className="bg-rouge-light text-rouge-primary p-4 rounded-md">{error}</div>;
    if (!stats) return <div className="text-center p-8">No data available.</div>;

    const serviceData = stats.by_service.map(item => ({ name: item.key, count: item.doc_count }));
    const timeData = stats.over_time.map(item => ({ time: new Date(item.key).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}), count: item.doc_count }));

    return (
        <div className="space-y-8">
            <div className="flex justify-between items-center">
                <h2 className="text-3xl font-bold text-noir-primary">DLQ Health Overview</h2>
                <div className="flex items-center space-x-2 text-sm">
                    <input type="datetime-local" name="date_start" value={filters.date_start} onChange={handleFilterChange} className="bg-white-primary border border-gris-blanc rounded-md px-2 py-1 focus:ring-orange-primary focus:border-orange-primary"/>
                    <span>to</span>
                    <input type="datetime-local" name="date_end" value={filters.date_end} onChange={handleFilterChange} className="bg-white-primary border border-gris-blanc rounded-md px-2 py-1 focus:ring-orange-primary focus:border-orange-primary"/>
                </div>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-white-primary p-6 rounded-lg shadow-md border border-clair-2">
                    <h3 className="text-lg font-medium text-gris-primary">Pending Messages (New)</h3>
                    <p className="text-5xl font-bold text-orange-primary mt-2">{stats.pending_count}</p>
                </div>
                <div className="bg-white-primary p-6 rounded-lg shadow-md border border-clair-2">
                    <h3 className="text-lg font-medium text-gris-primary mb-4">Top Errors</h3>
                    <table className="w-full text-sm text-left">
                        <tbody>
                        {stats.by_error.map((e, index) => 
                            <tr key={e.key} className={index % 2 === 0 ? 'bg-white-light' : 'bg-white-primary'}>
                                <td className="p-2 truncate">{e.key}</td>
                                <td className="p-2 text-right font-bold">{e.doc_count}</td>
                            </tr>
                        )}
                        </tbody>
                    </table>
                </div>
            </div>

            <div className="bg-white-primary p-6 rounded-lg shadow-md border border-clair-2">
                <h3 className="text-lg font-medium text-gris-primary mb-4">Failures by Service</h3>
                <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={serviceData} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
                        <XAxis dataKey="name" stroke="#BFBFBF" fontSize={12} />
                        <YAxis stroke="#BFBFBF" fontSize={12}/>
                        <Tooltip contentStyle={{ backgroundColor: '#FFF', border: '1px solid #E9E9E9' }} />
                        <Legend wrapperStyle={{fontSize: "14px"}}/>
                        <Bar dataKey="count" fill="#FB5607" />
                    </BarChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
}

export default Dashboard;