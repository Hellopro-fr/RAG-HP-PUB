"use client"

import * as React from "react";
import { useState, useEffect } from "react"
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts"
import { Button } from "@/components/ui/button"
import { apiGetDashboardStats, DashboardStats } from "@/lib/api";
import { DateTimePicker } from "./DateTimePicker";

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<{ date_start?: Date; date_end?: Date }>({});

  const fetchStats = async (currentFilters: { date_start?: Date; date_end?: Date }) => {
    try {
        setLoading(true);
        setError(null);
        const body: { date_start?: string, date_end?: string } = {};
        if (currentFilters.date_start) body.date_start = currentFilters.date_start.toISOString();
        if (currentFilters.date_end) body.date_end = currentFilters.date_end.toISOString();
        
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
    fetchStats({});
  }, []);

  const handleApplyFilter = () => {
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
    <div className="p-4 md:p-8 space-y-6 md:space-y-8">
      {/* Date Range Filter */}
      <div className="flex flex-col sm:flex-row flex-wrap gap-4 items-start sm:items-end">
        <div className="w-full sm:flex-1 min-w-[200px]">
          <label className="block text-sm font-medium text-noir-primary mb-2">From Date</label>
          <DateTimePicker 
            date={filters.date_start}
            setDate={(date) => setFilters(prev => ({ ...prev, date_start: date }))}
          />
        </div>
        <div className="w-full sm:flex-1 min-w-[200px]">
          <label className="block text-sm font-medium text-noir-primary mb-2">To Date</label>
          <DateTimePicker
            date={filters.date_end}
            setDate={(date) => setFilters(prev => ({ ...prev, date_end: date }))}
          />
        </div>
        <Button onClick={handleApplyFilter} style={{ backgroundColor: "var(--bleu-primary)", color: "white" }} className="w-full sm:w-auto hover:opacity-90">
          Apply Filter
        </Button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-6">
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
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
        {/* Service Breakdown Chart */}
        <div className="p-4 md:p-6 rounded-lg border border-gris-blanc bg-white-primary overflow-hidden w-full">
          <p className="text-sm font-medium text-noir-primary mb-4">Messages by Service</p>
          <div className="w-full h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
                <BarChart data={serviceData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--gris-blanc)" />
                <XAxis dataKey="name" fontSize={12} tickFormatter={(value) => value.substring(0, 10) + '...'} />
                <YAxis fontSize={12} />
                <Tooltip contentStyle={{ backgroundColor: "#fff", border: "1px solid var(--gris-blanc)" }} />
                <Bar dataKey="count" fill="var(--bleu-primary)" />
                </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Messages Over Time Chart */}
        <div className="p-4 md:p-6 rounded-lg border border-gris-blanc bg-white-primary overflow-hidden w-full">
          <p className="text-sm font-medium text-noir-primary mb-4">Pending Messages Over Time</p>
          <div className="w-full h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
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
    </div>
  )
}