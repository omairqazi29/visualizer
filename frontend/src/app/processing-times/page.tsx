"use client";

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { getProcessingTimes, ProcessingTimesData, ProcessingTimePoint } from '@/lib/api';
import {
  LineChart, Line, BarChart, Bar, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';

// Center colors (navy spectrum + crimson for worst)
const CENTER_COLORS: Record<string, string> = {
  TSC: '#059669',   // emerald (fastest)
  NSC: '#002868',   // navy
  PSC: '#6366f1',   // indigo
  NBC: '#BF0A30',   // crimson (slowest)
};

const CENTER_LABELS: Record<string, string> = {
  NSC: 'Nebraska',
  TSC: 'Texas',
  NBC: 'NBC',
  PSC: 'Potomac',
};

function formatMonth(dateStr: string): string {
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString(undefined, { month: 'short', year: '2-digit' });
}

export default function ProcessingTimesPage() {
  const [data, setData] = useState<ProcessingTimesData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string>('EB-1');

  useEffect(() => {
    getProcessingTimes()
      .then((d: ProcessingTimesData) => setData(d))
      .catch((e: unknown) => {
        const err = e as { message?: string };
        setError(err?.message || 'Failed to load processing times data');
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
        <div className="h-10 w-80 animate-pulse rounded bg-slate-200" />
        <div className="grid gap-4 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl border bg-slate-100" />
          ))}
        </div>
        <div className="h-[500px] animate-pulse rounded-xl border bg-slate-100" />
      </div>
    );
  }

  const { summary, time_series } = data;
  const isWorsening = summary.eb1_trend === 'worsening';

  // Build per-center time series for the selected category
  const dates = [...new Set(time_series.filter(r => r.category === selectedCategory).map(r => r.publication_date))].sort();
  const centers = summary.centers;

  const trendChart = dates.map(date => {
    const row: Record<string, string | number> = { date, label: formatMonth(date) };
    centers.forEach(center => {
      const point = time_series.find(r => r.publication_date === date && r.office_code === center && r.category === selectedCategory);
      if (point) {
        row[`${center}_mid`] = Math.round(((point.processing_time_min_months + point.processing_time_max_months) / 2) * 10) / 10;
        row[`${center}_min`] = point.processing_time_min_months;
        row[`${center}_max`] = point.processing_time_max_months;
      }
    });
    return row;
  });

  // Build comparison bar chart from latest data
  const latestByCategory = data.latest.filter(r => r.category === selectedCategory);
  const comparisonChart = latestByCategory
    .sort((a, b) => {
      const aMid = (a.processing_time_min_months + a.processing_time_max_months) / 2;
      const bMid = (b.processing_time_min_months + b.processing_time_max_months) / 2;
      return aMid - bMid;
    })
    .map(r => ({
      center: CENTER_LABELS[r.office_code] || r.office_code,
      code: r.office_code,
      min: r.processing_time_min_months,
      max: r.processing_time_max_months,
      midpoint: Math.round(((r.processing_time_min_months + r.processing_time_max_months) / 2) * 10) / 10,
      spread: Math.round((r.processing_time_max_months - r.processing_time_min_months) * 10) / 10,
    }));

  // Category breakdown from summary
  const categoryBreakdown = Object.entries(summary.by_category).map(([cat, info]) => ({
    category: cat,
    ...info,
  }));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-navy-900">
          Processing Times by Service Center
        </h2>
        <p className="text-slate-500">
          How fast each USCIS service center is adjudicating EB I-485s. Identifies domestic processing bottlenecks.
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card className={isWorsening ? 'border-crimson-200 bg-crimson-50/30' : 'border-emerald-200 bg-emerald-50/30'}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">EB-1 Trend</CardTitle>
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold capitalize ${isWorsening ? 'text-crimson-600' : 'text-emerald-600'}`}>
              {summary.eb1_trend}
            </div>
            <p className="text-sm text-slate-400">
              {summary.months_of_data} months of data
            </p>
          </CardContent>
        </Card>

        <Card className="border-emerald-200 bg-emerald-50/30">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">Fastest Center (EB-1)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-emerald-600">
              {summary.eb1_fastest_center_name}
            </div>
            <p className="text-sm text-slate-400">
              ~{summary.eb1_fastest_midpoint} mo avg
            </p>
          </CardContent>
        </Card>

        <Card className="border-crimson-200 bg-crimson-50/30">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">Slowest Center (EB-1)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-crimson-600">
              {summary.eb1_slowest_center_name}
            </div>
            <p className="text-sm text-slate-400">
              ~{summary.eb1_slowest_midpoint} mo avg
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">Center Gap (EB-1)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">
              {(summary.eb1_slowest_midpoint - summary.eb1_fastest_midpoint).toFixed(1)} mo
            </div>
            <p className="text-sm text-slate-400">
              slowest − fastest
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Category Filter */}
      <div className="flex gap-2">
        {['EB-1', 'EB-2', 'EB-3'].map(cat => (
          <button
            key={cat}
            onClick={() => setSelectedCategory(cat)}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              selectedCategory === cat
                ? 'bg-navy-900 text-white'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Chart 1: Processing Time Trends */}
      <Card className="p-6">
        <CardHeader>
          <CardTitle>{selectedCategory} Processing Time Trends</CardTitle>
          <CardDescription>
            Midpoint processing time (months) by service center over time. Lower is faster.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[450px] mt-4">
            <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
              <LineChart data={trendChart}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" minTickGap={30} />
                <YAxis
                  label={{ value: 'Months', angle: -90, position: 'insideLeft' }}
                  tickFormatter={(val) => `${val}`}
                />
                <Tooltip
                  contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                  formatter={(value, name) => {
                    const code = String(name).replace('_mid', '');
                    const label = CENTER_LABELS[code] || code;
                    return [`${value} months`, label];
                  }}
                  labelFormatter={(_label, items) =>
                    items[0]?.payload?.date || _label
                  }
                />
                <Legend
                  verticalAlign="top"
                  height={36}
                  formatter={(value) => {
                    const code = String(value).replace('_mid', '');
                    return CENTER_LABELS[code] || code;
                  }}
                />
                {centers.map(center => (
                  <Line
                    key={center}
                    type="monotone"
                    dataKey={`${center}_mid`}
                    stroke={CENTER_COLORS[center] || '#64748b'}
                    strokeWidth={2.5}
                    dot={{ r: 3 }}
                    activeDot={{ r: 5 }}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* Chart 2: Center Comparison (Bar) */}
      <Card className="p-6">
        <CardHeader>
          <CardTitle>{selectedCategory} Center Comparison (Latest)</CardTitle>
          <CardDescription>
            Processing time range at each service center. Shorter bars = faster processing.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[350px] mt-4">
            <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
              <BarChart data={comparisonChart} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <XAxis
                  type="number"
                  label={{ value: 'Months', position: 'insideBottom', offset: -5 }}
                />
                <YAxis type="category" dataKey="center" width={80} />
                <Tooltip
                  contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                  formatter={(value, name) => {
                    if (name === 'min') return [`${value} months`, 'Fastest'];
                    if (name === 'spread') return [`${value} months`, 'Range'];
                    return [`${value}`, String(name)];
                  }}
                />
                <Legend
                  verticalAlign="top"
                  height={36}
                  formatter={(value) => value === 'min' ? 'Min Processing Time' : 'Additional Range'}
                />
                <Bar dataKey="min" stackId="a" fill="#002868" radius={[4, 0, 0, 4]} />
                <Bar dataKey="spread" stackId="a" radius={[0, 4, 4, 0]}>
                  {comparisonChart.map((entry, index) => (
                    <Cell key={index} fill={CENTER_COLORS[entry.code] || '#94a3b8'} fillOpacity={0.4} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* Category Summary Table */}
      <Card className="p-6">
        <CardHeader>
          <CardTitle>Processing Bottleneck Summary</CardTitle>
          <CardDescription>
            Average processing times across all service centers, by EB category. Based on {summary.coverage}.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto mt-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200">
                  <th className="text-left py-3 px-4 font-medium text-slate-500">Category</th>
                  <th className="text-right py-3 px-4 font-medium text-slate-500">Avg Min</th>
                  <th className="text-right py-3 px-4 font-medium text-slate-500">Avg Max</th>
                  <th className="text-right py-3 px-4 font-medium text-slate-500">Midpoint</th>
                  <th className="text-right py-3 px-4 font-medium text-slate-500">Spread</th>
                  <th className="text-left py-3 px-4 font-medium text-slate-500">Fastest</th>
                  <th className="text-left py-3 px-4 font-medium text-slate-500">Slowest</th>
                </tr>
              </thead>
              <tbody>
                {categoryBreakdown.map(row => (
                  <tr key={row.category} className="border-b border-slate-100 hover:bg-slate-50">
                    <td className="py-3 px-4 font-medium text-navy-900">{row.category}</td>
                    <td className="text-right py-3 px-4">{row.avg_min_months} mo</td>
                    <td className="text-right py-3 px-4">{row.avg_max_months} mo</td>
                    <td className="text-right py-3 px-4 font-semibold">{row.avg_midpoint_months} mo</td>
                    <td className="text-right py-3 px-4 text-slate-400">{row.avg_spread_months} mo</td>
                    <td className="py-3 px-4">
                      <span className="inline-flex items-center rounded-full bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700">
                        {CENTER_LABELS[row.fastest_center] || row.fastest_center}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <span className="inline-flex items-center rounded-full bg-crimson-50 px-2 py-1 text-xs font-medium text-crimson-700">
                        {CENTER_LABELS[row.slowest_center] || row.slowest_center}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}