"use client";

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { getLegislation, LegislationData, LegislationBill, LegislationScenario } from '@/lib/api';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { cn } from '@/lib/utils';

const SCENARIO_COLORS: Record<string, string> = {
  eagle_act: '#2563eb',
  dignity_act: '#7c3aed',
  stem_pathway: '#059669',
  visa_recapture: '#d97706',
  h1b_reform: '#dc2626',
  combined_eagle_recapture: '#0891b2',
};

function getLikelihoodStyle(likelihood: string) {
  switch (likelihood) {
    case 'moderate':
      return 'bg-green-100 text-green-800';
    case 'low':
      return 'bg-amber-100 text-amber-800';
    case 'very_low':
      return 'bg-red-100 text-red-800';
    default:
      return 'bg-slate-100 text-slate-700';
  }
}

function getDirectionStyle(direction: string) {
  switch (direction) {
    case 'pro_immigration':
      return 'bg-blue-100 text-blue-800';
    case 'restrictionist':
      return 'bg-red-100 text-red-800';
    case 'mixed':
      return 'bg-slate-100 text-slate-700';
    default:
      return 'bg-slate-100 text-slate-700';
  }
}

function formatDirectionLabel(direction: string) {
  return direction.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function formatLikelihoodLabel(likelihood: string) {
  return likelihood.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString(undefined, { month: 'short', year: 'numeric', timeZone: 'UTC' });
}

function formatDateShort(dateStr: string) {
  return new Date(dateStr).toLocaleDateString(undefined, { month: 'short', year: '2-digit', timeZone: 'UTC' });
}

export default function LegislationPage() {
  const [data, setData] = useState<LegislationData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeScenarios, setActiveScenarios] = useState<Set<string>>(new Set(['eagle_act', 'visa_recapture']));

  useEffect(() => {
    getLegislation()
      .then((d: LegislationData) => setData(d))
      .catch((e: unknown) => {
        const err = e as { message?: string };
        setError(err?.message || 'Failed to load legislation data');
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
        <div className="h-5 w-96 animate-pulse rounded bg-slate-100" />
        <div className="grid gap-4 md:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-64 animate-pulse rounded-xl border bg-slate-100" />
          ))}
        </div>
        <div className="h-[400px] animate-pulse rounded-xl border bg-slate-100" />
      </div>
    );
  }

  const toggleScenario = (scenarioId: string) => {
    setActiveScenarios(prev => {
      const next = new Set(prev);
      if (next.has(scenarioId)) {
        next.delete(scenarioId);
      } else {
        next.add(scenarioId);
      }
      return next;
    });
  };

  // Build chart data: merge baseline + active scenario trajectories
  const baselineTrajectory = (data.baseline as { trajectory?: { date: string; backlog: number }[] }).trajectory || [];

  // Build a date-indexed map from baseline
  const chartMap = new Map<string, Record<string, number>>();
  baselineTrajectory.forEach((pt: { date: string; backlog: number }) => {
    chartMap.set(pt.date, { baseline: pt.backlog });
  });

  // Overlay each active scenario
  const activeScenarioList = Object.values(data.scenarios).filter(s => activeScenarios.has(s.scenario_id));
  activeScenarioList.forEach(scenario => {
    scenario.trajectory?.forEach(pt => {
      const entry = chartMap.get(pt.date) || {};
      entry[scenario.scenario_id] = pt.backlog;
      chartMap.set(pt.date, entry);
    });
  });

  const chartData = Array.from(chartMap.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, values]) => ({
      date,
      dateLabel: formatDateShort(date),
      baseline: values.baseline ?? null,
      ...Object.fromEntries(
        activeScenarioList.map(s => [s.scenario_id, values[s.scenario_id] ?? null])
      ),
    }));

  // Build summary table rows
  const allScenarios = Object.values(data.scenarios)
    .sort((a, b) => a.delta_months - b.delta_months);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-navy-900">Pending Legislation Tracker</h2>
        <p className="text-slate-500">
          Track bills that could change EB-1 India backlog timelines. Toggle scenarios to model their impact.
        </p>
      </div>

      {/* Bill Cards Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {data.bills.map((bill: LegislationBill) => {
          const isActive = bill.scenario_id ? activeScenarios.has(bill.scenario_id) : false;
          const scenarioColor = bill.scenario_id ? SCENARIO_COLORS[bill.scenario_id] || '#94a3b8' : undefined;
          const scenario = bill.scenario_id ? data.scenarios[bill.scenario_id] : null;

          return (
            <Card
              key={bill.id}
              className={cn(
                "transition-all hover:shadow-md",
                isActive && 'border-l-4',
              )}
              style={isActive && scenarioColor ? { borderLeftColor: scenarioColor } : undefined}
            >
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <CardTitle className="text-base font-semibold text-navy-900">
                      {bill.bill_number}
                    </CardTitle>
                    <CardDescription className="text-sm mt-0.5">
                      {bill.short_title}
                    </CardDescription>
                  </div>
                </div>
                <div className="flex flex-wrap gap-1.5 mt-2">
                  <Badge className={cn('text-[10px]', getLikelihoodStyle(bill.likelihood))}>
                    {formatLikelihoodLabel(bill.likelihood)}
                  </Badge>
                  <Badge className={cn('text-[10px]', getDirectionStyle(bill.direction))}>
                    {formatDirectionLabel(bill.direction)}
                  </Badge>
                  <Badge variant="outline" className="text-[10px]">
                    {bill.chamber}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="text-xs text-slate-500">
                  <span className="font-medium">Sponsor:</span> {bill.sponsor}
                  <span className="mx-2">·</span>
                  <span className="font-medium">Introduced:</span> {formatDate(bill.introduced)}
                </div>

                <div className="text-xs text-slate-500">
                  <span className="font-medium">Status:</span> {bill.status_detail}
                </div>

                {bill.key_provisions.length > 0 && (
                  <div>
                    <div className="text-xs font-medium text-slate-600 mb-1">Key Provisions</div>
                    <ul className="text-xs text-slate-500 space-y-0.5 list-disc list-inside">
                      {bill.key_provisions.map((prov, i) => (
                        <li key={i}>{prov}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {bill.impact_summary && (
                  <p className="text-xs text-slate-500 italic">{bill.impact_summary}</p>
                )}

                {bill.scenario_id && scenario && (
                  <Button
                    variant={isActive ? 'default' : 'outline'}
                    size="sm"
                    className="w-full mt-2"
                    onClick={() => toggleScenario(bill.scenario_id!)}
                    style={isActive && scenarioColor ? { backgroundColor: scenarioColor, borderColor: scenarioColor } : undefined}
                  >
                    {isActive ? '✓ Scenario Active' : 'Model This Scenario'}
                  </Button>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* What-If Scenario Comparison Chart */}
      <Card className="p-6">
        <CardHeader>
          <CardTitle>What-If Scenario Comparison</CardTitle>
          <CardDescription>
            Baseline trajectory (gray) vs. selected legislation scenarios. Toggle bills above to add/remove.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[450px] mt-4">
            <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="colorBaseline" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#94a3b8" stopOpacity={0.1} />
                    <stop offset="95%" stopColor="#94a3b8" stopOpacity={0} />
                  </linearGradient>
                  {activeScenarioList.map(scenario => (
                    <linearGradient key={scenario.scenario_id} id={`color_${scenario.scenario_id}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={SCENARIO_COLORS[scenario.scenario_id] || '#94a3b8'} stopOpacity={0.1} />
                      <stop offset="95%" stopColor={SCENARIO_COLORS[scenario.scenario_id] || '#94a3b8'} stopOpacity={0} />
                    </linearGradient>
                  ))}
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="dateLabel" minTickGap={30} />
                <YAxis tickFormatter={(val: number) => `${(val / 1000).toFixed(0)}k`} />
                <Tooltip
                  labelFormatter={(label, items) => items[0]?.payload?.date || label}
                  contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                  formatter={(value) => [(value ?? 0).toLocaleString(), 'Backlog']}
                />
                <Legend verticalAlign="top" height={36} />
                <Area
                  type="monotone"
                  dataKey="baseline"
                  name="Baseline"
                  stroke="#94a3b8"
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#colorBaseline)"
                  connectNulls
                />
                {activeScenarioList.map(scenario => (
                  <Area
                    key={scenario.scenario_id}
                    type="monotone"
                    dataKey={scenario.scenario_id}
                    name={scenario.scenario_name}
                    stroke={SCENARIO_COLORS[scenario.scenario_id] || '#94a3b8'}
                    strokeWidth={2}
                    fillOpacity={1}
                    fill={`url(#color_${scenario.scenario_id})`}
                    connectNulls
                  />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* Scenario Impact Summary Table */}
      <Card>
        <CardHeader>
          <CardTitle>Scenario Impact Summary</CardTitle>
          <CardDescription>
            Comparison of how each legislative scenario affects backlog clearance vs. baseline.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-3 px-4 font-medium text-slate-500">Scenario</th>
                  <th className="text-right py-3 px-4 font-medium text-slate-500">Annual Supply</th>
                  <th className="text-right py-3 px-4 font-medium text-slate-500">Clearance Date</th>
                  <th className="text-right py-3 px-4 font-medium text-slate-500">Time Saved</th>
                </tr>
              </thead>
              <tbody>
                {/* Baseline row */}
                <tr className="border-b bg-slate-50/50">
                  <td className="py-3 px-4 font-medium text-navy-900">
                    <div className="flex items-center gap-2">
                      <span className="w-3 h-3 rounded-full inline-block" style={{ backgroundColor: '#94a3b8' }} />
                      Baseline (Current Law)
                    </div>
                  </td>
                  <td className="text-right py-3 px-4 text-slate-700">
                    {data.baseline.annual_supply.toLocaleString()}
                  </td>
                  <td className="text-right py-3 px-4 text-slate-700">
                    {formatDate(data.baseline.clearance_date)}
                  </td>
                  <td className="text-right py-3 px-4 text-slate-400">—</td>
                </tr>
                {/* Scenario rows sorted by delta_months (most time saved first) */}
                {allScenarios.map((scenario: LegislationScenario) => {
                  const color = SCENARIO_COLORS[scenario.scenario_id] || '#94a3b8';
                  const isActive = activeScenarios.has(scenario.scenario_id);
                  const deltaMo = scenario.delta_months;
                  return (
                    <tr key={scenario.scenario_id} className={cn('border-b', isActive && 'bg-slate-50/30')}>
                      <td className="py-3 px-4 font-medium text-navy-900">
                        <div className="flex items-center gap-2">
                          <span className="w-3 h-3 rounded-full inline-block" style={{ backgroundColor: color }} />
                          {scenario.scenario_name}
                          {isActive && (
                            <Badge className="text-[10px] bg-slate-100 text-slate-600">Active</Badge>
                          )}
                        </div>
                      </td>
                      <td className="text-right py-3 px-4 text-slate-700">
                        {scenario.annual_supply.toLocaleString()}
                      </td>
                      <td className="text-right py-3 px-4 text-slate-700">
                        {formatDate(scenario.clearance_date)}
                      </td>
                      <td className={cn(
                        'text-right py-3 px-4 font-semibold',
                        deltaMo < 0 ? 'text-green-600' : deltaMo > 0 ? 'text-red-600' : 'text-slate-400'
                      )}>
                        {deltaMo < 0
                          ? `${Math.abs(deltaMo)} mo. faster`
                          : deltaMo > 0
                            ? `${deltaMo} mo. slower`
                            : '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Last updated footer */}
      {data.last_updated && (
        <div className="text-xs text-slate-400 text-right">
          Last updated: {formatDate(data.last_updated)}
        </div>
      )}
    </div>
  );
}