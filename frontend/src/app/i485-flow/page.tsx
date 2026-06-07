"use client";

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { getI485Flow, I485FlowData } from '@/lib/api';
import {
  ComposedChart, Bar, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';

function formatPeriod(year: number, month: number): string {
  return new Date(year, month - 1).toLocaleDateString(undefined, {
    month: 'short',
    year: '2-digit',
  });
}

export default function I485FlowPage() {
  const [data, setData] = useState<I485FlowData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getI485Flow()
      .then((d: I485FlowData) => setData(d))
      .catch((e: unknown) => {
        const err = e as { message?: string };
        setError(err?.message || 'Failed to load I-485 flow data');
      });
  }, []);

  if (error) {
    return (
      <div className="rounded-lg border border-crimson-200 bg-crimson-50 p-4 text-crimson-700">
        {error}
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-6">
        <div className="h-10 w-64 animate-pulse rounded bg-slate-200" />
        <div className="grid gap-4 md:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-20 animate-pulse rounded-xl border bg-slate-100" />
          ))}
        </div>
        <div className="h-[500px] animate-pulse rounded-xl border bg-slate-100" />
      </div>
    );
  }

  const { summary } = data;
  const isGrowing = summary.queue_trend === 'growing';

  const monthlyChart = data.monthly.map((point) => ({
    ...point,
    label: formatPeriod(point.year, point.month),
  }));

  const totalChart = data.monthly.map((point) => ({
    ...point,
    label: formatPeriod(point.year, point.month),
  }));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-navy-900">
          I-485 Receipts vs. Approvals
        </h2>
        <p className="text-slate-500">
          Monthly inflow (new demand) vs. outflow (approvals). Shows whether the I-485 queue is growing or shrinking.
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card className={isGrowing ? 'border-crimson-200 bg-crimson-50/30' : 'border-emerald-200 bg-emerald-50/30'}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">EB Queue Trend</CardTitle>
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${isGrowing ? 'text-crimson-600' : 'text-emerald-600'}`}>
              {isGrowing ? 'Growing' : 'Shrinking'}
            </div>
            <p className={`text-sm ${isGrowing ? 'text-crimson-500' : 'text-emerald-500'}`}>
              {summary.pending_trend_pct > 0 ? '+' : ''}{summary.pending_trend_pct.toFixed(1)}% trend
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">EB Pending</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">
              {summary.latest_eb_pending.toLocaleString()}
            </div>
            <p className="text-sm text-slate-400">
              as of {summary.latest_period}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">Avg Monthly EB Net Flow</CardTitle>
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${summary.avg_monthly_eb_net_flow > 0 ? 'text-crimson-600' : 'text-emerald-600'}`}>
              {summary.avg_monthly_eb_net_flow > 0 ? '+' : ''}{Math.round(summary.avg_monthly_eb_net_flow).toLocaleString()}
            </div>
            <p className="text-sm text-slate-400">
              receipts minus approvals/mo
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Chart 1: Employment-Based I-485 Flow */}
      <Card className="p-6">
        <CardHeader>
          <CardTitle>Employment-Based I-485 Flow</CardTitle>
          <CardDescription>Monthly EB receipts (new filings) vs. approvals. Side-by-side comparison of inflow and outflow.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[450px] mt-4">
            <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
              <ComposedChart data={monthlyChart}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" minTickGap={30} />
                <YAxis tickFormatter={(val) => `${(Number(val) / 1000).toFixed(0)}k`} />
                <Tooltip
                  contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                  formatter={(value, name) => [
                    (value ?? 0).toLocaleString(),
                    name === 'eb_receipts' ? 'EB Receipts' : name === 'eb_approvals' ? 'EB Approvals' : name,
                  ]}
                  labelFormatter={(_label, items) =>
                    items[0]?.payload?.period || _label
                  }
                />
                <Legend
                  verticalAlign="top"
                  height={36}
                  formatter={(value) =>
                    value === 'eb_receipts' ? 'EB Receipts' : value === 'eb_approvals' ? 'EB Approvals' : value
                  }
                />
                <Bar dataKey="eb_receipts" fill="#002868" radius={[2, 2, 0, 0]} barSize={20} />
                <Bar dataKey="eb_approvals" fill="#059669" radius={[2, 2, 0, 0]} barSize={20} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* Chart 2: EB Pending Backlog Trend */}
      <Card className="p-6">
        <CardHeader>
          <CardTitle>EB Pending Backlog Trend</CardTitle>
          <CardDescription>Total employment-based I-485 cases pending at USCIS over time.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[400px] mt-4">
            <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
              <AreaChart data={monthlyChart}>
                <defs>
                  <linearGradient id="colorPending" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#BF0A30" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="#BF0A30" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" minTickGap={30} />
                <YAxis tickFormatter={(val) => `${(Number(val) / 1000).toFixed(0)}k`} />
                <Tooltip
                  contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                  formatter={(value) => [(value ?? 0).toLocaleString(), 'EB Pending']}
                  labelFormatter={(_label, items) =>
                    items[0]?.payload?.period || _label
                  }
                />
                <Legend verticalAlign="top" height={36} formatter={() => 'EB Pending Cases'} />
                <Area
                  type="monotone"
                  dataKey="eb_pending"
                  stroke="#BF0A30"
                  strokeWidth={3}
                  fillOpacity={1}
                  fill="url(#colorPending)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* Chart 3: All I-485 Categories Flow */}
      <Card className="p-6">
        <CardHeader>
          <CardTitle>All I-485 Categories Flow</CardTitle>
          <CardDescription>Total I-485 receipts vs. approvals across all categories (EB + FB + other).</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[380px] mt-4">
            <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
              <ComposedChart data={totalChart}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" minTickGap={30} />
                <YAxis tickFormatter={(val) => `${(Number(val) / 1000).toFixed(0)}k`} />
                <Tooltip
                  contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                  formatter={(value, name) => [
                    (value ?? 0).toLocaleString(),
                    name === 'total_receipts' ? 'Total Receipts' : name === 'total_approvals' ? 'Total Approvals' : name,
                  ]}
                  labelFormatter={(_label, items) =>
                    items[0]?.payload?.period || _label
                  }
                />
                <Legend
                  verticalAlign="top"
                  height={36}
                  formatter={(value) =>
                    value === 'total_receipts' ? 'Total Receipts' : value === 'total_approvals' ? 'Total Approvals' : value
                  }
                />
                <Bar dataKey="total_receipts" fill="#475569" radius={[2, 2, 0, 0]} barSize={20} />
                <Bar dataKey="total_approvals" fill="#94a3b8" radius={[2, 2, 0, 0]} barSize={20} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}