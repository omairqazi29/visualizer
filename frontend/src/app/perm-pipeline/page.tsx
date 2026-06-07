"use client";

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { getPERMPipeline, PERMPipelineData } from '@/lib/api';
import {
  BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
  PieChart, Pie, Cell,
} from 'recharts';

const COLORS = {
  india: '#BF0A30',
  china: '#002868',
  row: '#94a3b8',
  eb2: '#002868',
  eb3: '#059669',
  unknown: '#cbd5e1',
  certified: '#059669',
  certifiedExpired: '#86efac',
  denied: '#BF0A30',
  withdrawn: '#f59e0b',
  other: '#94a3b8',
};

export default function PERMPipelinePage() {
  const [data, setData] = useState<PERMPipelineData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getPERMPipeline()
      .then((d: PERMPipelineData) => setData(d))
      .catch((e: unknown) => {
        const err = e as { message?: string };
        setError(err?.message || 'Failed to load PERM pipeline data');
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
  const hasIndiaLatest = summary.india_latest && 'total' in summary.india_latest;

  // Prepare chart data — for FYs without country data, show total as "unknown_country"
  const fyChart = data.by_fy.map((d) => ({
    ...d,
    label: `FY${d.fiscal_year}`,
    unknown_country: d.has_country_data ? 0 : d.total,
    // Zero out country breakdown when data isn't available
    india: d.has_country_data ? d.india : 0,
    china: d.has_country_data ? d.china : 0,
    row: d.has_country_data ? d.row : 0,
  }));

  const indiaPipelineChart = data.india_pipeline.map((d) => ({
    ...d,
    label: `FY${d.fiscal_year}`,
  }));

  const categoryChart = data.by_category.map((d) => ({
    ...d,
    label: `FY${d.fiscal_year}`,
  }));

  const statusChart = data.status_breakdown.map((d) => ({
    ...d,
    label: `FY${d.fiscal_year}`,
  }));

  // Top countries for pie chart
  const pieData = data.top_countries.slice(0, 8).map((d) => ({
    name: d.country,
    value: d.total,
    pct: d.pct,
  }));
  const PIE_COLORS = ['#BF0A30', '#002868', '#059669', '#f59e0b', '#8b5cf6', '#ec4899', '#14b8a6', '#94a3b8'];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-navy-900">
          PERM Labor Certification Pipeline
        </h2>
        <p className="text-slate-500">
          DOL PERM certifications are a 12-24 month leading indicator of future EB-2/EB-3 I-140 filings.
          Each certified PERM represents a future visa demand entering the EB system.
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">Total Certified PERMs</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">
              {summary.total_certified.toLocaleString()}
            </div>
            <p className="text-sm text-slate-400">
              across FY{summary.fiscal_years[0]}–FY{summary.fiscal_years[summary.fiscal_years.length - 1]}
            </p>
          </CardContent>
        </Card>

        <Card className="border-crimson-200 bg-crimson-50/30">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">India Certified PERMs</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-crimson-600">
              {summary.total_india_certified.toLocaleString()}
            </div>
            <p className="text-sm text-crimson-400">
              {summary.total_certified > 0
                ? `${((summary.total_india_certified / summary.total_certified) * 100).toFixed(1)}% of total`
                : ''}
            </p>
          </CardContent>
        </Card>

        {hasIndiaLatest && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-slate-500">
                India FY{summary.india_latest.fiscal_year}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-navy-900">
                {summary.india_latest.total.toLocaleString()}
              </div>
              <p className="text-sm text-slate-400">
                EB-2: {summary.india_latest.eb2.toLocaleString()} | EB-3: {summary.india_latest.eb3.toLocaleString()}
              </p>
            </CardContent>
          </Card>
        )}

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">India YoY Growth</CardTitle>
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${
              summary.india_yoy_growth_pct !== null && summary.india_yoy_growth_pct > 0
                ? 'text-crimson-600'
                : 'text-emerald-600'
            }`}>
              {summary.india_yoy_growth_pct !== null
                ? `${summary.india_yoy_growth_pct > 0 ? '+' : ''}${summary.india_yoy_growth_pct}%`
                : 'N/A'}
            </div>
            <p className="text-sm text-slate-400">
              latest vs. prior FY
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Chart 1: Certified PERMs by FY and Country */}
      <Card className="p-6">
        <CardHeader>
          <CardTitle>Certified PERMs by Fiscal Year</CardTitle>
          <CardDescription>
            Stacked by country of citizenship. India dominates EB PERM filings — each represents a future I-140 petition.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[450px] mt-4">
            <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
              <BarChart data={fyChart}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" />
                <YAxis tickFormatter={(val) => `${(Number(val) / 1000).toFixed(0)}k`} />
                <Tooltip
                  contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                  formatter={(value, name) => {
                    const v = Number(value ?? 0);
                    if (v === 0) return ['', ''];
                    const labels: Record<string, string> = {
                      india: 'India',
                      china: 'China',
                      row: 'Rest of World',
                      unknown_country: 'Total (country N/A)',
                    };
                    return [v.toLocaleString(), labels[String(name)] || String(name)];
                  }}
                />
                <Legend
                  verticalAlign="top"
                  height={36}
                  formatter={(value: string) => {
                    const labels: Record<string, string> = {
                      india: 'India',
                      china: 'China',
                      row: 'Rest of World',
                      unknown_country: 'Country N/A (new form)',
                    };
                    return labels[value] || value;
                  }}
                />
                <Bar dataKey="india" stackId="a" fill={COLORS.india} />
                <Bar dataKey="china" stackId="a" fill={COLORS.china} />
                <Bar dataKey="row" stackId="a" fill={COLORS.row} />
                <Bar dataKey="unknown_country" stackId="a" fill="#e2e8f0" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* Chart 2: India EB Pipeline by Category */}
      <Card className="p-6">
        <CardHeader>
          <CardTitle>India PERM Pipeline — EB-2 vs. EB-3</CardTitle>
          <CardDescription>
            India certified PERMs split by inferred EB category (based on minimum education requirement).
            These cases will become I-140 filings within 12-24 months.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[400px] mt-4">
            <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
              <BarChart data={indiaPipelineChart}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" />
                <YAxis tickFormatter={(val) => `${(Number(val) / 1000).toFixed(0)}k`} />
                <Tooltip
                  contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                  formatter={(value, name) => [
                    (value ?? 0).toLocaleString(),
                    String(name) === 'eb2' ? 'EB-2 (Advanced Degree)' : String(name) === 'eb3' ? 'EB-3 (Skilled/Professional)' : 'Unknown',
                  ]}
                />
                <Legend
                  verticalAlign="top"
                  height={36}
                  formatter={(value: string) =>
                    value === 'eb2' ? 'EB-2 (Advanced Degree)' : value === 'eb3' ? 'EB-3 (Skilled/Professional)' : 'Unknown'
                  }
                />
                <Bar dataKey="eb2" stackId="a" fill={COLORS.eb2} />
                <Bar dataKey="eb3" stackId="a" fill={COLORS.eb3} />
                <Bar dataKey="unknown" stackId="a" fill={COLORS.unknown} radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Chart 3: Approval Rate / Status Breakdown */}
        <Card className="p-6">
          <CardHeader>
            <CardTitle>Case Outcomes by Fiscal Year</CardTitle>
            <CardDescription>
              Certified vs. denied vs. withdrawn. High approval rates indicate strong pipeline flow.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[350px] mt-4">
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
                <BarChart data={statusChart}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="label" />
                  <YAxis tickFormatter={(val) => `${(Number(val) / 1000).toFixed(0)}k`} />
                  <Tooltip
                    contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                    formatter={(value, name) => {
                      const labels: Record<string, string> = {
                        certified: 'Certified (Active)',
                        certified_expired: 'Certified (Expired)',
                        denied: 'Denied',
                        withdrawn: 'Withdrawn',
                      };
                      return [(value ?? 0).toLocaleString(), labels[String(name)] || String(name)];
                    }}
                  />
                  <Legend
                    verticalAlign="top"
                    height={36}
                    formatter={(value: string) => {
                      const labels: Record<string, string> = {
                        certified: 'Certified (Active)',
                        certified_expired: 'Certified (Expired)',
                        denied: 'Denied',
                        withdrawn: 'Withdrawn',
                      };
                      return labels[value] || value;
                    }}
                  />
                  <Bar dataKey="certified" stackId="a" fill={COLORS.certified} />
                  <Bar dataKey="certified_expired" stackId="a" fill={COLORS.certifiedExpired} />
                  <Bar dataKey="denied" stackId="a" fill={COLORS.denied} />
                  <Bar dataKey="withdrawn" stackId="a" fill={COLORS.withdrawn} radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Chart 4: Top Countries Pie */}
        <Card className="p-6">
          <CardHeader>
            <CardTitle>Top Countries by Certified PERMs</CardTitle>
            <CardDescription>
              Share of certified PERM labor certifications by country of citizenship (all years combined).
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
                    formatter={(value) => [(value ?? 0).toLocaleString(), 'Certified PERMs']}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* All-Country Category Breakdown */}
      <Card className="p-6">
        <CardHeader>
          <CardTitle>All Countries — EB-2 vs. EB-3 Split</CardTitle>
          <CardDescription>
            Worldwide certified PERMs by inferred EB category. Shows the overall mix of advanced-degree (EB-2)
            vs. skilled-worker (EB-3) demand entering the system.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[380px] mt-4">
            <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
              <BarChart data={categoryChart}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" />
                <YAxis tickFormatter={(val) => `${(Number(val) / 1000).toFixed(0)}k`} />
                <Tooltip
                  contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                  formatter={(value, name) => [
                    (value ?? 0).toLocaleString(),
                    String(name) === 'eb2' ? 'EB-2' : String(name) === 'eb3' ? 'EB-3' : 'Unknown',
                  ]}
                />
                <Legend
                  verticalAlign="top"
                  height={36}
                  formatter={(value: string) =>
                    value === 'eb2' ? 'EB-2 (Advanced Degree)' : value === 'eb3' ? 'EB-3 (Skilled/Professional)' : 'Unknown'
                  }
                />
                <Bar dataKey="eb2" fill={COLORS.eb2} radius={[2, 2, 0, 0]} barSize={40} />
                <Bar dataKey="eb3" fill={COLORS.eb3} radius={[2, 2, 0, 0]} barSize={40} />
                <Bar dataKey="unknown" fill={COLORS.unknown} radius={[2, 2, 0, 0]} barSize={40} />
              </BarChart>
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
            <strong>Source:</strong> DOL OFLC PERM Disclosure Data, published quarterly at{' '}
            <a href="https://www.dol.gov/agencies/eta/foreign-labor/performance" target="_blank" rel="noopener noreferrer" className="text-navy-700 underline">
              dol.gov/agencies/eta/foreign-labor/performance
            </a>
          </p>
          <p>
            <strong>EB Category Inference:</strong> EB-2 vs. EB-3 is inferred from the minimum education
            requirement on the PERM application. Master&apos;s/Doctorate/Professional = EB-2; Bachelor&apos;s and below = EB-3.
            The actual EB category is determined at the I-140 stage and may differ.
          </p>
          <p>
            <strong>Pipeline Lag:</strong> A certified PERM typically leads to an I-140 filing within 12-24 months.
            This data represents future demand that has not yet entered the I-140 pipeline or the visa backlog.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}