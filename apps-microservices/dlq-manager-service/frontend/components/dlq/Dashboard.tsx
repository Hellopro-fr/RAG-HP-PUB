"use client"

import * as React from "react";
import { useState, useEffect } from "react"
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts"
import { Button } from "@/components/ui/button"
import { Calendar } from "lucide-react"
import { apiGetDashboardStats, DashboardStats } from "@/lib/api";

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState({ date_start: "", date_end: "" });

  // Modified to accept filters as an argument to prevent stale state issues.
  const fetchStats = async (currentFilters: { date_start: string; date_end: string }) => {
    try {
        setLoading(true);
        setError(null);
        const body: { date_start?: string, date_end?: string } = {};
        if (currentFilters.date_start) body.date_start = new Date(currentFilters.date_start).toISOString();
        if (currentFilters.date_end) body.date_end = new Date(currentFilters.date_end).toISOString();
        
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
    // Initial fetch on component mount with default empty filters.
    fetchStats({ date_start: "", date_end: "" });
  }, []);

  const handleFilterChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFilters(prev => ({...prev, [e.target.name]: e.target.value}));
  };

  const handleApplyFilter = () => {
      // Pass the current, up-to-date filters state directly to the fetch function.
      fetchStats(filters);
  }

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center h-full">
        <div className="text-gris-primary">Loading dashboard...</div>
      </div>
    )
  }

  if (error || !stats) {
    return (
      <div className="p-8 flex items-center justify-center h-full">
        <div className="text-rouge-primary">{error || 'Failed to load dashboard'}</div>
      </div>
    )
  }

  const serviceData = stats.by_service.map(item => ({ name: item.key, count: item.doc_count }));
  const timeData = stats.over_time.map(item => ({
      time: new Date(item.key).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      count: item.doc_count
  }));


  return (
    <div className="p-8 space-y-8">
      {/* Date Range Filter */}
      <div className="flex gap-4 items-end">
        <div className="flex-1 max-w-xs">
          <label className="block text-sm font-medium text-noir-primary mb-2">From Date</label>
          <div className="relative">
            <Calendar className="absolute left-3 top-3 w-4 h-4 text-gris-primary" />
            <input
              type="datetime-local"
              name="date_start"
              value={filters.date_start}
              onChange={handleFilterChange}
              className="w-full pl-10 pr-4 py-2 border border-gris-blanc rounded-lg bg-white-primary text-noir-primary"
            />
          </div>
        </div>
        <div className="flex-1 max-w-xs">
          <label className="block text-sm font-medium text-noir-primary mb-2">To Date</label>
          <div className="relative">
            <Calendar className="absolute left-3 top-3 w-4 h-4 text-gris-primary" />
            <input
              type="datetime-local"
              name="date_end"
              value={filters.date_end}
              onChange={handleFilterChange}
              className="w-full pl-10 pr-4 py-2 border border-gris-blanc rounded-lg bg-white-primary text-noir-primary"
            />
          </div>
        </div>
        <Button onClick={handleApplyFilter} style={{ backgroundColor: "var(--bleu-primary)", color: "white" }} className="hover:opacity-90">
          Apply Filter
        </Button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Total Pending Messages */}
        <div className="p-6 rounded-lg border border-gris-blanc" style={{ backgroundColor: "var(--bleu-light)" }}>
          <p className="text-sm font-medium text-gris-primary mb-2">Total Pending Messages</p>
          <p className="text-4xl font-bold" style={{ color: "var(--bleu-primary)" }}>
            {stats.pending_count.toLocaleString()}
          </p>
        </div>

        {/* Top Errors */}
        <div className="p-6 rounded-lg border border-gris-blanc bg-white-primary">
          <p className="text-sm font-medium text-noir-primary mb-4">Top 5 Errors</p>
          <div className="space-y-3">
            {stats.by_error.slice(0, 5).map((error) => (
              <div key={error.key} className="flex justify-between items-center text-sm">
                <span className="text-gris-primary truncate flex-1" title={error.key}>{error.key}</span>
                <span
                  className="font-semibold ml-2 px-3 py-1 rounded"
                  style={{ backgroundColor: "var(--rouge-light)", color: "var(--rouge-primary)" }}
                >
                  {error.doc_count}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Service Breakdown Chart */}
        <div className="p-6 rounded-lg border border-gris-blanc bg-white-primary">
          <p className="text-sm font-medium text-noir-primary mb-4">Messages by Service</p>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={serviceData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--gris-blanc)" />
              <XAxis dataKey="name" fontSize={12} />
              <YAxis fontSize={12} />
              <Tooltip contentStyle={{ backgroundColor: "#fff", border: "1px solid var(--gris-blanc)" }} />
              <Bar dataKey="count" fill="var(--bleu-primary)" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Messages Over Time Chart */}
        <div className="p-6 rounded-lg border border-gris-blanc bg-white-primary">
          <p className="text-sm font-medium text-noir-primary mb-4">Pending Messages Over Time</p>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={timeData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--gris-blanc)" />
              <XAxis dataKey="time" fontSize={12} />
              <YAxis fontSize={12} />
              <Tooltip contentStyle={{ backgroundColor: "#fff", border: "1px solid var(--gris-blanc)" }} />
              <Line
                type="monotone"
                dataKey="count"
                stroke="var(--bleu-primary)"
                dot={{ fill: "var(--bleu-primary)" }}
                strokeWidth={2}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}