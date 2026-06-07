"use client";

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { getCEACScheduling, CEACSchedulingData } from '@/lib/api';
import {
  BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
  ComposedChart, Area,
} from 'recharts';

const COLORS = {
  india: '#BF0A30',
  global: '#002868',
  principal: '#059669',
  derivative: '#f59e0b',
  creation: '#6366f1',
  review: '#BF0A30',
  inquiry: '#059669',
};

export default function CEACSchedulingPage() {
  const [data, setData] = useState<CEACSchedulingData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCEACScheduling()
      .then((d: CEACSchedulingData) => setData(d))
      .catch((e: unknown) => {
        const err = e as { message?: string };
        setError(err?.message || 'Failed to load CEAC scheduling data');
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
  const latestFY = summary.latest_complete_fy;

  // India monthly issuance chart — downsample to show recent years
  const indiaMonthly = data.india_monthly.map((d) => ({
    ...d,
    label: d.month,
    derivative: d.eb1_issuances - d.eb1_principal,
  }));

  // FY comparison chart (global + India)
  const fyChart = data.fiscal_year_data.map((d) => ({
    label: `FY${d.fiscal_year}`,
    ...d,
    non_india_eb1: d.total_eb1 - d.india_eb1,
    india_pct: d.total_eb1 > 0 ? Math.round(d.india_eb1 / d.total_eb1 * 1000) / 10 : 0,
  }));

  // Top posts bar chart
  const topPostsChart = data.top_posts.slice(0, 15).map((d) => ({
    name: d.post_name,
    total: d.total_eb1,
    principal: d.total_principal,
    derivative: d.total_eb1 - d.total_principal,
  }));

  // NVC wait times — downsample to monthly for chart readability
  const nvcChart: { date: string; creation?: number; review?: number; inquiry?: number }[] = [];
  if (data.nvc_wait_times.creation) {
    const monthlyMap: Record<string, { creation?: number; review?: number; inquiry?: number }> = {};
    for (const queue of ['creation', 'review', 'inquiry'] as const) {
      const points = data.nvc_wait_times[queue] || [];
      for (const p of points) {
        const month = p.date.slice(0, 7);
        if (!monthlyMap[month]) monthlyMap[month] = {};
        // Take the last value in each month
        monthlyMap[month][queue] = p.days;
      }
    }
    for (const [date, vals] of Object.entries(monthlyMap).sort()) {
      nvcChart.push({ date, ...vals });
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-navy-900">
          CEAC Interview Scheduling
        </h2>
        <p className="text-slate-500">
          Scraped consular appointment data showing real-time consular pipeline activity.
          Validates DOS IV issuance projections with ground-truth consulate-level issuance
          counts and NVC processing wait times.
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">
              Data Coverage
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">
              {data.data_range.posts}
            </div>
            <p className="text-sm text-slate-400">
              consulates tracked ({data.data_range.start?.slice(0, 7)} to {data.data_range.end?.slice(0, 7)})
            </p>
          </CardContent>
        </Card>

        <Card className="border-crimson-200 bg-crimson-50/30">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">
              India EB-1 (FY{latestFY?.fiscal_year})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-crimson-600">
              {(latestFY?.india_eb1 ?? 0).toLocaleString()}
            </div>
            <p className="text-sm text-crimson-400">
              of {(latestFY?.total_eb1 ?? 0).toLocaleString()} global EB-1
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">
              Global EB-1 (FY{latestFY?.fiscal_year})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">
              {(latestFY?.total_eb1 ?? 0).toLocaleString()}
            </div>
            <p className="text-sm text-slate-400">
              {(latestFY?.principal_eb1 ?? 0).toLocaleString()} principals
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">
              NVC Review Wait
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">
              {data.nvc_latest.review ?? 'N/A'}{data.nvc_latest.review ? ' days' : ''}
            </div>
            <p className="text-sm text-slate-400">
              creation: {data.nvc_latest.creation ?? 'N/A'} days
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Chart 1: EB-1 Issuances by Fiscal Year (Global vs India) */}
      <Card className="p-6">
        <CardHeader>
          <CardTitle>EB-1 Consular Issuances by Fiscal Year</CardTitle>
          <CardDescription>
            Consulate-level EB-1 visa issuances worldwide vs. India. Use this to cross-reference
            and validate the DOS monthly IV issuance reports used in the supply model.
            FY2020-2021 shows COVID-era consulate closures.
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
                    const labels: Record<string, string> = {
                      india_eb1: 'India EB-1',
                      non_india_eb1: 'Rest of World EB-1',
                    };
                    return [(value ?? 0).toLocaleString(), labels[String(name)] || String(name)];
                  }}
                />
                <Legend
                  verticalAlign="top"
                  height={36}
                  formatter={(value: string) => {
                    const labels: Record<string, string> = {
                      india_eb1: 'India EB-1',
                      non_india_eb1: 'Rest of World',
                    };
                    return labels[value] || value;
                  }}
                />
                <Bar dataKey="india_eb1" stackId="a" fill={COLORS.india} />
                <Bar dataKey="non_india_eb1" stackId="a" fill="#cbd5e1" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* Chart 2: India Monthly EB-1 Issuances */}
      <Card className="p-6">
        <CardHeader>
          <CardTitle>India EB-1 Monthly Consular Issuances</CardTitle>
          <CardDescription>
            Monthly EB-1 visa issuances across all 5 Indian consulates (Mumbai, Chennai,
            Hyderabad, Kolkata, New Delhi). Shows consular processing velocity — the
            actual rate at which visas flow through Indian posts.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[400px] mt-4">
            <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
              <ComposedChart data={indiaMonthly}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="label"
                  interval={11}
                  tick={{ fontSize: 12 }}
                />
                <YAxis />
                <Tooltip
                  contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                  formatter={(value, name) => {
                    const labels: Record<string, string> = {
                      eb1_principal: 'Principals (E11/E12/E13)',
                      derivative: 'Derivatives (Spouse/Child)',
                    };
                    return [(value ?? 0).toLocaleString(), labels[String(name)] || String(name)];
                  }}
                />
                <Legend
                  verticalAlign="top"
                  height={36}
                  formatter={(value: string) => {
                    const labels: Record<string, string> = {
                      eb1_principal: 'Principals',
                      derivative: 'Derivatives',
                    };
                    return labels[value] || value;
                  }}
                />
                <Area dataKey="derivative" stackId="a" fill="#fef3c7" stroke={COLORS.derivative} strokeWidth={1} />
                <Area dataKey="eb1_principal" stackId="a" fill="#dcfce7" stroke={COLORS.principal} strokeWidth={2} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Chart 3: Top Consulates by EB-1 Issuances */}
        <Card className="p-6">
          <CardHeader>
            <CardTitle>Top Consulates by EB-1 Volume</CardTitle>
            <CardDescription>
              Which consulates issue the most EB-1 visas worldwide. India&apos;s 5 posts
              appear alongside other high-volume consulates.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[450px] mt-4">
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
                <BarChart data={topPostsChart} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickFormatter={(val) => val.toLocaleString()} />
                  <YAxis dataKey="name" type="category" width={120} tick={{ fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                    formatter={(value, name) => {
                      const labels: Record<string, string> = {
                        principal: 'Principals',
                        derivative: 'Derivatives',
                      };
                      return [(value ?? 0).toLocaleString(), labels[String(name)] || String(name)];
                    }}
                  />
                  <Legend verticalAlign="top" height={36} />
                  <Bar dataKey="principal" stackId="a" fill={COLORS.principal} />
                  <Bar dataKey="derivative" stackId="a" fill={COLORS.derivative} radius={[0, 2, 2, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Chart 4: NVC Wait Times */}
        {nvcChart.length > 0 && (
          <Card className="p-6">
            <CardHeader>
              <CardTitle>NVC Processing Wait Times</CardTitle>
              <CardDescription>
                How long the National Visa Center takes for case creation, document review,
                and inquiry response. Longer wait times indicate a bottleneck between
                I-140 approval and consular interview scheduling.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="h-[450px] mt-4">
                <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
                  <LineChart data={nvcChart}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis
                      dataKey="date"
                      interval={5}
                      tick={{ fontSize: 11 }}
                    />
                    <YAxis
                      label={{ value: 'Days', angle: -90, position: 'insideLeft' }}
                    />
                    <Tooltip
                      contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                      formatter={(value, name) => {
                        const labels: Record<string, string> = {
                          creation: 'Case Creation',
                          review: 'Document Review',
                          inquiry: 'Inquiry Response',
                        };
                        return [`${value} days`, labels[String(name)] || String(name)];
                      }}
                    />
                    <Legend
                      verticalAlign="top"
                      height={36}
                      formatter={(value: string) => {
                        const labels: Record<string, string> = {
                          creation: 'Case Creation',
                          review: 'Document Review',
                          inquiry: 'Inquiry Response',
                        };
                        return labels[value] || value;
                      }}
                    />
                    <Line dataKey="creation" stroke={COLORS.creation} strokeWidth={2} dot={false} />
                    <Line dataKey="review" stroke={COLORS.review} strokeWidth={2} dot={false} />
                    <Line dataKey="inquiry" stroke={COLORS.inquiry} strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {/* India EB-1 Share Over Time */}
      <Card className="p-6">
        <CardHeader>
          <CardTitle>India Share of Global EB-1 Consular Issuances</CardTitle>
          <CardDescription>
            India&apos;s share of worldwide EB-1 consular issuances by fiscal year.
            Cross-reference with DOS Report of the Visa Office data to validate
            the supply model&apos;s India EB-1 allocation assumptions.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[380px] mt-4">
            <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
              <ComposedChart data={fyChart.filter(d => d.total_eb1 > 0)}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" />
                <YAxis
                  yAxisId="left"
                  tickFormatter={(val) => `${(Number(val) / 1000).toFixed(0)}k`}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  tickFormatter={(val) => `${val}%`}
                  domain={[0, 40]}
                />
                <Tooltip
                  contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                  formatter={(value, name) => {
                    if (String(name) === 'india_pct') return [`${value}%`, 'India Share'];
                    if (String(name) === 'total_eb1') return [(value ?? 0).toLocaleString(), 'Global EB-1'];
                    if (String(name) === 'india_eb1') return [(value ?? 0).toLocaleString(), 'India EB-1'];
                    return [(value ?? 0).toLocaleString(), String(name)];
                  }}
                />
                <Legend
                  verticalAlign="top"
                  height={36}
                  formatter={(value: string) => {
                    const labels: Record<string, string> = {
                      total_eb1: 'Global EB-1',
                      india_eb1: 'India EB-1',
                      india_pct: 'India Share %',
                    };
                    return labels[value] || value;
                  }}
                />
                <Bar yAxisId="left" dataKey="total_eb1" fill="#e2e8f0" radius={[2, 2, 0, 0]} barSize={35} />
                <Bar yAxisId="left" dataKey="india_eb1" fill={COLORS.india} radius={[2, 2, 0, 0]} barSize={35} />
                <Line
                  yAxisId="right"
                  dataKey="india_pct"
                  stroke={COLORS.india}
                  strokeWidth={2}
                  dot={{ r: 4 }}
                />
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
            <strong>Data Source:</strong> Scraped consular appointment data from{' '}
            <a href="https://visawhen.com" target="_blank" rel="noopener noreferrer"
              className="text-navy-700 underline">visawhen.com</a>{' '}
            (GitHub:{' '}
            <a href="https://github.com/underyx/visawhen" target="_blank" rel="noopener noreferrer"
              className="text-navy-700 underline">underyx/visawhen</a>).
            Automated scraping from DOS consular data via GitHub Actions.
          </p>
          <p>
            <strong>Coverage:</strong> {data.data_range.posts} consulates worldwide,
            {' '}{data.data_range.start?.slice(0, 7)} to {data.data_range.end?.slice(0, 7)}.
            EB categories: EB-1 (E11/E12/E13 + derivatives), EW3 (other workers), EB-4, EB-5.
          </p>
          <p>
            <strong>Why This Matters:</strong> This consulate-level data complements the
            DOS monthly IV issuance files (which aggregate by country). By comparing
            consulate-level issuances with the country-level DOS reports, you can validate
            the supply model&apos;s IV issuance projections and identify consular processing
            bottlenecks at specific posts.
          </p>
          <p>
            <strong>Limitation:</strong> EB-2 and EB-3 &quot;skilled worker&quot; categories
            are not available in this consulate-level dataset. The DOS monthly country-level
            files remain the primary source for those categories.
          </p>
          <p>
            <strong>India Consulates:</strong> Mumbai, Chennai, Hyderabad, Kolkata, New Delhi.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}