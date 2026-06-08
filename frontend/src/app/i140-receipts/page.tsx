"use client";

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { getI140Receipts, I140ReceiptsData } from '@/lib/api';
import {
  BarChart, Bar, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
  PieChart, Pie, Cell, ComposedChart, Area,
} from 'recharts';

const COLORS = {
  eb1: '#BF0A30',
  eb2: '#002868',
  eb3: '#059669',
  india: '#BF0A30',
  china: '#002868',
  philippines: '#f59e0b',
  brazil: '#059669',
  vietnam: '#8b5cf6',
  approved: '#059669',
  denied: '#ef4444',
  pending: '#f59e0b',
  receipts: '#002868',
};

export default function I140ReceiptsPage() {
  const [data, setData] = useState<I140ReceiptsData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getI140Receipts()
      .then((d: I140ReceiptsData) => setData(d))
      .catch((e: unknown) => {
        const err = e as { message?: string };
        setError(err?.message || 'Failed to load I-140 receipts data');
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
        <div className="grid gap-4 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-20 animate-pulse rounded-xl border bg-slate-100" />
          ))}
        </div>
        <div className="h-[500px] animate-pulse rounded-xl border bg-slate-100" />
      </div>
    );
  }

  const { summary } = data;
  const indiaGrowth = summary.india_queue_growth;

  // Chart 1: All countries receipts over time with EB breakdown
  const allChart = data.all_countries.map((d) => ({
    label: `FY${d.fiscal_year}`,
    ...d,
  }));

  // Chart 2: India receipts with EB breakdown
  const indiaChart = data.india.map((d) => ({
    label: `FY${d.fiscal_year}`,
    ...d,
  }));

  // Chart 3: YoY growth rates
  const growthChart = data.india_growth_rates
    .filter((d) => d.yoy_growth_pct !== null)
    .map((d) => ({
      label: `FY${d.fiscal_year}`,
      ...d,
    }));

  // Chart 4: Country comparison pie
  const pieData = data.country_comparison.map((d) => ({
    name: d.country,
    value: d.receipts,
    pct: d.share_pct,
  }));
  const PIE_COLORS = ['#BF0A30', '#002868', '#f59e0b', '#059669', '#8b5cf6', '#94a3b8'];

  // Chart 5: Status breakdown (approved/denied/pending) for India
  const statusChart = data.india.map((d) => ({
    label: `FY${d.fiscal_year}`,
    approved: d.approved,
    denied: d.denied,
    pending: d.pending,
    approval_rate: d.approval_rate,
  }));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-navy-900">
          I-140 Receipts (New Filings)
        </h2>
        <p className="text-slate-500">
          New I-140 petitions entering the system — separate from approved/pipeline.
          Each receipt is a new EB green card petition filed with USCIS.
          This models the queue growth rate: how fast is new demand entering the system?
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">
              FY{summary.latest_fy} Total Receipts
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">
              {summary.latest_total_receipts.toLocaleString()}
            </div>
            <p className="text-sm text-slate-400">
              All countries, all categories
            </p>
          </CardContent>
        </Card>

        <Card className="border-crimson-200 bg-crimson-50/30">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">
              India FY{indiaGrowth.latest_fy} Receipts
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-crimson-600">
              {indiaGrowth.latest_receipts.toLocaleString()}
            </div>
            <p className="text-sm text-crimson-400">
              {indiaGrowth.india_share_pct}% of all I-140 filings
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">India YoY Growth</CardTitle>
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${
              indiaGrowth.yoy_growth_pct !== null && indiaGrowth.yoy_growth_pct > 0
                ? 'text-crimson-600'
                : 'text-emerald-600'
            }`}>
              {indiaGrowth.yoy_growth_pct !== null
                ? `${indiaGrowth.yoy_growth_pct > 0 ? '+' : ''}${indiaGrowth.yoy_growth_pct}%`
                : 'N/A'}
            </div>
            <p className="text-sm text-slate-400">
              5yr CAGR: {indiaGrowth.cagr_5yr_pct}%
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">Pending (All FYs)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-amber-600">
              {indiaGrowth.total_pending_all_fy.toLocaleString()}
            </div>
            <p className="text-sm text-slate-400">
              India I-140s unresolved
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Chart 1: All Countries I-140 Receipts by EB Category */}
      <Card className="p-6">
        <CardHeader>
          <CardTitle>All Countries — I-140 New Filings by EB Category</CardTitle>
          <CardDescription>
            Total new I-140 petitions filed each fiscal year, broken down by EB preference category.
            The dramatic rise from FY2022 onward reflects both organic demand growth and
            the post-COVID filing surge. FY2025 reached 244,844 — an all-time high.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[450px] mt-4">
            <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
              <BarChart data={allChart}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" />
                <YAxis tickFormatter={(val) => `${(Number(val) / 1000).toFixed(0)}k`} />
                <Tooltip
                  contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                  formatter={(value, name) => {
                    const labels: Record<string, string> = {
                      eb1_receipts: 'EB-1 (Priority Workers)',
                      eb2_receipts: 'EB-2 (Advanced Degree)',
                      eb3_receipts: 'EB-3 (Skilled Workers)',
                    };
                    return [(value ?? 0).toLocaleString(), labels[String(name)] || String(name)];
                  }}
                />
                <Legend
                  verticalAlign="top"
                  height={36}
                  formatter={(value: string) => {
                    const labels: Record<string, string> = {
                      eb1_receipts: 'EB-1',
                      eb2_receipts: 'EB-2',
                      eb3_receipts: 'EB-3',
                    };
                    return labels[value] || value;
                  }}
                />
                <Bar dataKey="eb1_receipts" stackId="a" fill={COLORS.eb1} />
                <Bar dataKey="eb2_receipts" stackId="a" fill={COLORS.eb2} />
                <Bar dataKey="eb3_receipts" stackId="a" fill={COLORS.eb3} radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* Chart 2: India I-140 Receipts by EB Category */}
      <Card className="p-6">
        <CardHeader>
          <CardTitle>India — I-140 New Filings by EB Category</CardTitle>
          <CardDescription>
            India-specific I-140 new filings. India accounts for ~{indiaGrowth.india_share_pct}% of all
            I-140 filings. EB-2 dominates India filings (mostly PERM-based), while EB-1 shows
            the fastest growth rate. Each filing adds to the future visa queue.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[450px] mt-4">
            <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
              <BarChart data={indiaChart}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" />
                <YAxis tickFormatter={(val) => `${(Number(val) / 1000).toFixed(0)}k`} />
                <Tooltip
                  contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                  formatter={(value, name) => {
                    const labels: Record<string, string> = {
                      eb1_receipts: 'EB-1 (Priority Workers)',
                      eb2_receipts: 'EB-2 (Advanced Degree)',
                      eb3_receipts: 'EB-3 (Skilled Workers)',
                    };
                    return [(value ?? 0).toLocaleString(), labels[String(name)] || String(name)];
                  }}
                />
                <Legend
                  verticalAlign="top"
                  height={36}
                  formatter={(value: string) => {
                    const labels: Record<string, string> = {
                      eb1_receipts: 'EB-1',
                      eb2_receipts: 'EB-2',
                      eb3_receipts: 'EB-3',
                    };
                    return labels[value] || value;
                  }}
                />
                <Bar dataKey="eb1_receipts" stackId="a" fill={COLORS.eb1} />
                <Bar dataKey="eb2_receipts" stackId="a" fill={COLORS.eb2} />
                <Bar dataKey="eb3_receipts" stackId="a" fill={COLORS.eb3} radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Chart 3: India YoY Growth Rates by Category */}
        <Card className="p-6">
          <CardHeader>
            <CardTitle>India I-140 Filing Growth Rate</CardTitle>
            <CardDescription>
              Year-over-year growth in India I-140 filings by EB category.
              Positive values = queue growing faster. Sustained growth means
              the backlog is compounding despite visa issuances.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[350px] mt-4">
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
                <ComposedChart data={growthChart}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="label" />
                  <YAxis tickFormatter={(val) => `${val}%`} />
                  <Tooltip
                    contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                    formatter={(value, name) => {
                      const labels: Record<string, string> = {
                        yoy_growth_pct: 'Overall Growth',
                        eb1_growth_pct: 'EB-1 Growth',
                        eb2_growth_pct: 'EB-2 Growth',
                        eb3_growth_pct: 'EB-3 Growth',
                      };
                      return [value !== null ? `${value}%` : 'N/A', labels[String(name)] || String(name)];
                    }}
                  />
                  <Legend
                    verticalAlign="top"
                    height={36}
                    formatter={(value: string) => {
                      const labels: Record<string, string> = {
                        yoy_growth_pct: 'Overall',
                        eb1_growth_pct: 'EB-1',
                        eb2_growth_pct: 'EB-2',
                        eb3_growth_pct: 'EB-3',
                      };
                      return labels[value] || value;
                    }}
                  />
                  <Line dataKey="yoy_growth_pct" stroke="#002868" strokeWidth={2} dot={{ r: 4 }} />
                  <Line dataKey="eb1_growth_pct" stroke={COLORS.eb1} strokeWidth={1.5} dot={{ r: 3 }} strokeDasharray="4 2" />
                  <Line dataKey="eb2_growth_pct" stroke={COLORS.eb2} strokeWidth={1.5} dot={{ r: 3 }} strokeDasharray="4 2" />
                  <Line dataKey="eb3_growth_pct" stroke={COLORS.eb3} strokeWidth={1.5} dot={{ r: 3 }} strokeDasharray="4 2" />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Chart 4: Country Share Pie */}
        <Card className="p-6">
          <CardHeader>
            <CardTitle>I-140 Filings by Country (FY{summary.latest_fy})</CardTitle>
            <CardDescription>
              Distribution of new I-140 petitions by country of birth.
              India is the single largest source of new EB petitions.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[350px] mt-4">
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    outerRadius={120}
                    dataKey="value"
                    label={({ name, payload }) => `${name} (${payload?.pct ?? 0}%)`}
                    labelLine={true}
                  >
                    {pieData.map((_entry, index) => (
                      <Cell key={`cell-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                    formatter={(value) => [(value ?? 0).toLocaleString(), 'Receipts']}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Chart 5: India I-140 Status Breakdown (Approved/Denied/Pending) */}
      <Card className="p-6">
        <CardHeader>
          <CardTitle>India I-140 Petition Outcomes Over Time</CardTitle>
          <CardDescription>
            How India I-140 petitions are resolved each fiscal year. Rising &quot;pending&quot; counts
            (amber) indicate USCIS processing backlog growing faster than adjudication capacity.
            The FY2024-2025 pending spike reflects both volume increase and processing slowdowns.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[450px] mt-4">
            <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
              <ComposedChart data={statusChart}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" />
                <YAxis yAxisId="left" tickFormatter={(val) => `${(Number(val) / 1000).toFixed(0)}k`} />
                <YAxis yAxisId="right" orientation="right" tickFormatter={(val) => `${val}%`} domain={[0, 100]} />
                <Tooltip
                  contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                  formatter={(value, name) => {
                    const labels: Record<string, string> = {
                      approved: 'Approved',
                      denied: 'Denied',
                      pending: 'Pending/Other',
                      approval_rate: 'Approval Rate',
                    };
                    if (String(name) === 'approval_rate') return [`${value}%`, labels[String(name)]];
                    return [(value ?? 0).toLocaleString(), labels[String(name)] || String(name)];
                  }}
                />
                <Legend
                  verticalAlign="top"
                  height={36}
                  formatter={(value: string) => {
                    const labels: Record<string, string> = {
                      approved: 'Approved',
                      denied: 'Denied',
                      pending: 'Pending',
                      approval_rate: 'Approval Rate %',
                    };
                    return labels[value] || value;
                  }}
                />
                <Bar yAxisId="left" dataKey="approved" stackId="a" fill={COLORS.approved} />
                <Bar yAxisId="left" dataKey="denied" stackId="a" fill={COLORS.denied} />
                <Bar yAxisId="left" dataKey="pending" stackId="a" fill={COLORS.pending} radius={[2, 2, 0, 0]} />
                <Line yAxisId="right" dataKey="approval_rate" stroke="#002868" strokeWidth={2} dot={{ r: 4 }} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* Methodology note */}
      <Card className="p-6 border-slate-200 bg-slate-50/50">
        <CardHeader>
          <CardTitle className="text-base">About This Data</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-slate-600 space-y-2">
          <p>
            <strong>Source:</strong> USCIS &quot;Number of Form I-140, Immigrant Petition for Alien Worker
            Petitions Received and Current Status&quot; — published quarterly at{' '}
            <a href="https://www.uscis.gov/tools/reports-and-studies/immigration-and-citizenship-data"
              target="_blank" rel="noopener noreferrer" className="text-navy-700 underline">
              uscis.gov/immigration-and-citizenship-data
            </a>.
          </p>
          <p>
            <strong>Receipts vs. Pipeline:</strong> This page shows <em>new filings</em> (receipts) —
            how many I-140 petitions are being filed. This is different from the &quot;pipeline&quot; data
            (shown in Supply/Demand), which counts <em>approved</em> I-140s waiting for visa numbers.
            Receipts model queue growth rate; pipeline models current queue depth.
          </p>
          <p>
            <strong>Why This Matters:</strong> Even if USCIS approves visas faster, the backlog only
            shrinks if approvals exceed new filings. Sustained receipt growth (especially India EB-2)
            means the queue compounds year over year. The 5-year CAGR shows this structural growth trend.
          </p>
          <p>
            <strong>Coverage:</strong> FY2014–FY2025 (Q1-Q4). Countries: All Countries, India, China,
            Philippines, Brazil, Vietnam. Categories: EB-1, EB-2, EB-3, EB-4, EB-5.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}