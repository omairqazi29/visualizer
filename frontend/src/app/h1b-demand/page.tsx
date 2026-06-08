"use client";

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { getH1BDemand, H1BDemandData } from '@/lib/api';
import {
  BarChart, Bar, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
  PieChart, Pie, Cell, ComposedChart, Area,
} from 'recharts';

const COLORS = {
  india: '#BF0A30',
  china: '#002868',
  row: '#94a3b8',
  selected: '#059669',
  registrations: '#002868',
  eligible: '#6366f1',
  initial: '#BF0A30',
  continuing: '#f59e0b',
  multiple: '#ef4444',
  unique: '#059669',
};

export default function H1BDemandPage() {
  const [data, setData] = useState<H1BDemandData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getH1BDemand()
      .then((d: H1BDemandData) => setData(d))
      .catch((e: unknown) => {
        const err = e as { message?: string };
        setError(err?.message || 'Failed to load H-1B demand data');
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

  // Prepare cap registration chart data
  const regChart = data.cap_registrations.map((d) => ({
    label: `FY${d.fiscal_year}`,
    ...d,
    unselected: d.eligible_registrations - d.selected_registrations,
  }));

  // India demand pressure chart
  const indiaChart = data.india_demand.map((d) => ({
    label: `FY${d.fiscal_year}`,
    ...d,
  }));

  // Selection rate + multiple registration rate trend
  const trendChart = data.cap_registrations.map((d) => ({
    label: `FY${d.fiscal_year}`,
    selection_rate: d.selection_rate,
    multiple_reg_pct: d.multiple_reg_pct,
    unique_beneficiaries: d.unique_beneficiaries,
  }));

  // Top countries pie
  const pieData = data.top_countries.map((d) => ({
    name: d.country,
    value: d.approvals,
    pct: d.share_pct,
  }));
  const PIE_COLORS = ['#BF0A30', '#002868', '#059669', '#f59e0b', '#8b5cf6', '#ec4899', '#14b8a6', '#94a3b8'];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-navy-900">
          H-1B Demand Pressure
        </h2>
        <p className="text-slate-500">
          H-1B cap registrations and approvals are a leading indicator of future I-140 filings.
          Most India EB-1/2/3 cases flow through H-1B first — each approved H-1B is a 2-5 year leading
          indicator of a future EB green card petition.
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">
              FY{summary.latest_reg_fy} Registrations
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">
              {summary.latest_total_registrations.toLocaleString()}
            </div>
            <p className="text-sm text-slate-400">
              {summary.registration_yoy_growth_pct !== null
                ? `${summary.registration_yoy_growth_pct > 0 ? '+' : ''}${summary.registration_yoy_growth_pct}% YoY`
                : ''}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">
              FY{summary.latest_reg_fy} Selection Rate
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">
              {summary.latest_selection_rate}%
            </div>
            <p className="text-sm text-slate-400">
              {summary.latest_selected.toLocaleString()} selected
            </p>
          </CardContent>
        </Card>

        <Card className="border-crimson-200 bg-crimson-50/30">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">
              India FY{summary.latest_approval_fy} Approvals
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-crimson-600">
              {summary.latest_india_approvals.toLocaleString()}
            </div>
            <p className="text-sm text-crimson-400">
              {summary.latest_india_share_pct}% of all H-1B approvals
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">India Approval YoY</CardTitle>
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
              initial: {summary.latest_india_initial.toLocaleString()} new H-1Bs
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Chart 1: Cap Registrations vs. Selections */}
      <Card className="p-6">
        <CardHeader>
          <CardTitle>H-1B Cap Registrations vs. Selections</CardTitle>
          <CardDescription>
            Total eligible registrations vs. lottery-selected. The gap shows unmet H-1B demand —
            rejected registrants may retry, seek other visas, or leave the US workforce.
            FY2024 spike reflects mass gaming via multiple registrations (now curbed).
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[450px] mt-4">
            <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
              <BarChart data={regChart}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" />
                <YAxis tickFormatter={(val) => `${(Number(val) / 1000).toFixed(0)}k`} />
                <Tooltip
                  contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                  formatter={(value, name) => {
                    const labels: Record<string, string> = {
                      selected_registrations: 'Selected (Lottery Winners)',
                      unselected: 'Not Selected',
                    };
                    return [(value ?? 0).toLocaleString(), labels[String(name)] || String(name)];
                  }}
                />
                <Legend
                  verticalAlign="top"
                  height={36}
                  formatter={(value: string) => {
                    const labels: Record<string, string> = {
                      selected_registrations: 'Selected',
                      unselected: 'Not Selected',
                    };
                    return labels[value] || value;
                  }}
                />
                <Bar dataKey="selected_registrations" stackId="a" fill={COLORS.selected} />
                <Bar dataKey="unselected" stackId="a" fill="#e2e8f0" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* Chart 2: India H-1B Approvals (Initial vs Continuing) */}
      <Card className="p-6">
        <CardHeader>
          <CardTitle>India H-1B Approvals — Initial vs. Continuing</CardTitle>
          <CardDescription>
            Initial approvals = new H-1B holders entering the system (future I-140 demand).
            Continuing = renewals/extensions of existing H-1B holders already in the EB pipeline.
            Each initial approval is a 2-5 year leading indicator of an I-140 filing.
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
                      india_initial: 'Initial (New H-1Bs)',
                      india_continuing: 'Continuing (Extensions)',
                    };
                    return [(value ?? 0).toLocaleString(), labels[String(name)] || String(name)];
                  }}
                />
                <Legend
                  verticalAlign="top"
                  height={36}
                  formatter={(value: string) => {
                    const labels: Record<string, string> = {
                      india_initial: 'Initial (New H-1Bs)',
                      india_continuing: 'Continuing (Extensions)',
                    };
                    return labels[value] || value;
                  }}
                />
                <Bar dataKey="india_initial" stackId="a" fill={COLORS.initial} />
                <Bar dataKey="india_continuing" stackId="a" fill={COLORS.continuing} radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Chart 3: Selection Rate & Multiple Registration Trend */}
        <Card className="p-6">
          <CardHeader>
            <CardTitle>Selection Rate & Gaming Indicator</CardTitle>
            <CardDescription>
              Selection rate (green) shows lottery odds. Multiple registration % (red) reveals
              system gaming — FY2024 saw 54% multiple registrations before USCIS tightened rules.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[350px] mt-4">
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
                <ComposedChart data={trendChart}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="label" />
                  <YAxis tickFormatter={(val) => `${val}%`} domain={[0, 60]} />
                  <Tooltip
                    contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                    formatter={(value, name) => {
                      const labels: Record<string, string> = {
                        selection_rate: 'Selection Rate',
                        multiple_reg_pct: 'Multiple Registration %',
                      };
                      return [`${value}%`, labels[String(name)] || String(name)];
                    }}
                  />
                  <Legend
                    verticalAlign="top"
                    height={36}
                    formatter={(value: string) => {
                      const labels: Record<string, string> = {
                        selection_rate: 'Selection Rate',
                        multiple_reg_pct: 'Multiple Reg %',
                      };
                      return labels[value] || value;
                    }}
                  />
                  <Area dataKey="selection_rate" fill="#dcfce7" stroke={COLORS.selected} strokeWidth={2} />
                  <Line dataKey="multiple_reg_pct" stroke={COLORS.multiple} strokeWidth={2} dot={{ r: 4 }} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Chart 4: Top Countries Pie */}
        <Card className="p-6">
          <CardHeader>
            <CardTitle>H-1B Approvals by Country (FY{summary.latest_approval_fy})</CardTitle>
            <CardDescription>
              India dominates H-1B approvals at ~70%. Each India H-1B holder is a potential
              future EB green card applicant, feeding the I-140 pipeline.
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
                    formatter={(value) => [(value ?? 0).toLocaleString(), 'Approvals']}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Chart 5: India Share % Over Time */}
      <Card className="p-6">
        <CardHeader>
          <CardTitle>India Share of H-1B Approvals Over Time</CardTitle>
          <CardDescription>
            India&apos;s share of all H-1B approvals across fiscal years. A sustained ~70% share means
            the vast majority of future EB demand pressure originates from India-born H-1B holders.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[380px] mt-4">
            <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
              <ComposedChart data={indiaChart}>
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
                  domain={[60, 80]}
                />
                <Tooltip
                  contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                  formatter={(value, name) => {
                    if (String(name) === 'india_share_pct') return [`${value}%`, 'India Share'];
                    if (String(name) === 'india_approvals') return [(value ?? 0).toLocaleString(), 'India Approvals'];
                    if (String(name) === 'total_approvals') return [(value ?? 0).toLocaleString(), 'Total Approvals'];
                    return [(value ?? 0).toLocaleString(), String(name)];
                  }}
                />
                <Legend
                  verticalAlign="top"
                  height={36}
                  formatter={(value: string) => {
                    const labels: Record<string, string> = {
                      total_approvals: 'Total Approvals',
                      india_approvals: 'India Approvals',
                      india_share_pct: 'India Share %',
                    };
                    return labels[value] || value;
                  }}
                />
                <Bar yAxisId="left" dataKey="total_approvals" fill="#e2e8f0" radius={[2, 2, 0, 0]} barSize={35} />
                <Bar yAxisId="left" dataKey="india_approvals" fill={COLORS.india} radius={[2, 2, 0, 0]} barSize={35} />
                <Line yAxisId="right" dataKey="india_share_pct" stroke={COLORS.india} strokeWidth={2} dot={{ r: 4 }} />
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
            <strong>Cap Registration Source:</strong> USCIS H-1B Electronic Registration Process page.
            Published annually at{' '}
            <a href="https://www.uscis.gov/working-in-the-united-states/temporary-workers/h-1b-specialty-occupations/h-1b-electronic-registration-process"
              target="_blank" rel="noopener noreferrer" className="text-navy-700 underline">
              uscis.gov
            </a>. Electronic registration began FY2021.
          </p>
          <p>
            <strong>Approval Data Source:</strong> &quot;Characteristics of H-1B Specialty Occupation Workers&quot;
            annual Congressional reports. Published at{' '}
            <a href="https://www.uscis.gov/tools/reports-and-studies" target="_blank" rel="noopener noreferrer"
              className="text-navy-700 underline">
              uscis.gov/tools/reports-and-studies
            </a>.
          </p>
          <p>
            <strong>Why This Matters for EB Green Cards:</strong> H-1B is the primary nonimmigrant visa for
            specialty occupation workers. Most India EB-1, EB-2, and EB-3 green card applicants held or hold H-1B status.
            Initial H-1B approvals are a 2-5 year leading indicator of future I-140 petition filings —
            the first step in the EB green card process.
          </p>
          <p>
            <strong>Limitation:</strong> USCIS does not publish cap registration data broken down by country of birth.
            Country shares are available only from the annual Characteristics reports (approval data).
          </p>
        </CardContent>
      </Card>
    </div>
  );
}