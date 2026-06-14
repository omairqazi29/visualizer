"use client";

import { useEffect, useState, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getOppenheimPrediction, OppenheimData } from '@/lib/api';
import {
  ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { Crosshair, TrendingUp, AlertTriangle, BarChart3, Info } from 'lucide-react';

const CATEGORIES = ['EB-1', 'EB-2', 'EB-3'] as const;

function formatDateTick(ts: number): string {
  if (!ts || !isFinite(ts)) return '';
  const d = new Date(ts);
  return d.toLocaleDateString(undefined, { month: 'short', year: 'numeric', timeZone: 'UTC' });
}

function formatMonthLabel(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString(undefined, { month: 'short', year: '2-digit', timeZone: 'UTC' });
}

function formatDateDisplay(dateStr: string | null | undefined): string {
  if (!dateStr) return '—';
  const d = new Date(dateStr);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
}

function safeParse(dateStr: string | null | undefined): number | null {
  if (!dateStr) return null;
  const t = new Date(dateStr).getTime();
  return isFinite(t) ? t : null;
}

export default function OppenheimPage() {
  const [category, setCategory] = useState<string>('EB-1');
  const [applyRestrictions, setApplyRestrictions] = useState(true);
  const [monthsAhead, setMonthsAhead] = useState(12);
  const [data, setData] = useState<OppenheimData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getOppenheimPrediction(category, monthsAhead, undefined, applyRestrictions)
      .then(setData)
      .catch((err: unknown) => {
        const e = err as { response?: { data?: { detail?: string } }; message?: string };
        setError(e?.response?.data?.detail || e?.message || 'Failed to load prediction');
      })
      .finally(() => setLoading(false));
  }, [category, monthsAhead, applyRestrictions]);

  const chartData = useMemo(() => {
    if (!data?.trajectory) return [];
    return data.trajectory.map(pt => ({
      month: pt.bulletin_month,
      label: formatMonthLabel(pt.bulletin_month),
      fad: safeParse(pt.predicted_fad),
      fadLow: safeParse(pt.fad_low),
      fadHigh: safeParse(pt.fad_high),
      isCurrent: pt.is_current,
    }));
  }, [data]);

  const cal = data?.calibration;
  const next = data?.next_fad;

  // Loading skeleton
  if (loading && !data) {
    return (
      <div className="space-y-6 max-w-6xl">
        <div>
          <div className="h-10 w-72 animate-pulse rounded bg-slate-200" />
          <div className="h-5 w-96 animate-pulse rounded bg-slate-100 mt-2" />
        </div>
        <div className="flex gap-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-10 w-20 animate-pulse rounded-md bg-slate-200" />
          ))}
        </div>
        <div className="h-[450px] animate-pulse rounded-xl border bg-slate-100" />
        <div className="grid gap-4 md:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl border bg-slate-100" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-6xl">
      {/* Header */}
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-navy-900 flex items-center gap-2">
          <Crosshair className="w-8 h-8 text-navy-800" />
          Oppenheim FAD Solver
        </h2>
        <p className="text-slate-500 mt-1">
          Predicts the <span className="font-semibold">Final Action Date</span> using DOS&apos;s demand-supply equilibrium algorithm &mdash;
          the same math Charlie Oppenheim uses to set cutoff dates each month.
        </p>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex gap-2">
          {CATEGORIES.map(cat => (
            <button
              key={cat}
              onClick={() => setCategory(cat)}
              className={`px-4 py-2 text-sm font-semibold rounded-md transition-colors ${
                category === cat
                  ? 'bg-navy-900 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-navy-900'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>

        {/* Months ahead selector */}
        <select
          value={monthsAhead}
          onChange={e => setMonthsAhead(Number(e.target.value))}
          className="px-3 py-2 text-sm rounded-md border border-slate-200 bg-white text-slate-700"
        >
          <option value={6}>6 months</option>
          <option value={12}>12 months</option>
          <option value={24}>24 months</option>
          <option value={36}>36 months</option>
        </select>

        {/* Restrictions toggle */}
        <label className="flex items-center gap-2 cursor-pointer select-none ml-2">
          <div className="relative">
            <input
              type="checkbox"
              checked={applyRestrictions}
              onChange={(e) => setApplyRestrictions(e.target.checked)}
              className="sr-only peer"
            />
            <div className="w-9 h-5 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:bg-crimson-600 transition-colors" />
            <div className="absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full transition-transform peer-checked:translate-x-4" />
          </div>
          <span className="text-sm text-slate-600">Current Policy (91 Countries)</span>
        </label>

        {loading && (
          <span className="text-xs text-slate-400 animate-pulse ml-2">Updating...</span>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-crimson-200 bg-crimson-50 p-4 text-crimson-700 flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 flex-shrink-0" />
          {error}
        </div>
      )}

      {data && (
        <>
          {/* Calibration summary bar */}
          {cal && next && (
            <Card className="border-slate-200 bg-slate-50/50">
              <CardContent className="pt-5 pb-4">
                <div className="flex flex-wrap items-center gap-6 text-sm">
                  <div>
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Current FAD</span>
                    <p className="font-semibold text-navy-900">{formatDateDisplay(cal.current_fad)}</p>
                  </div>
                  <div>
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Predicted Next</span>
                    <p className="font-semibold text-navy-900">
                      {next.is_current ? 'Current' : formatDateDisplay(next.predicted_fad)}
                    </p>
                  </div>
                  {next.advancement_days !== null && next.advancement_days !== undefined && (
                    <div>
                      <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Advancement</span>
                      <p className={`font-semibold ${next.advancement_days > 0 ? 'text-emerald-700' : next.advancement_days < 0 ? 'text-crimson-600' : 'text-slate-500'}`}>
                        {next.advancement_days > 0 ? '+' : ''}{next.advancement_days} days
                      </p>
                    </div>
                  )}
                  <div>
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Confidence Range</span>
                    <p className="font-semibold text-slate-600 text-xs">
                      {formatDateDisplay(next.fad_low)} &ndash; {formatDateDisplay(next.fad_high)}
                    </p>
                  </div>
                  <Badge variant="outline" className="text-xs">{data.category} &mdash; {data.country}</Badge>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Stats cards */}
          {cal && (
            <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-6">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-slate-500">Materialization Rate</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-navy-900">{(cal.calibrated_rate * 100).toFixed(1)}%</div>
                  <p className="text-xs text-slate-400">calibrated from VB</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-slate-500">Annual Supply</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-navy-900">{cal.annual_supply.toLocaleString()}</div>
                  <p className="text-xs text-slate-400">India {data.category} visas</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-slate-500">Monthly Target</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-navy-900">{Math.round(cal.monthly_supply).toLocaleString()}</div>
                  <p className="text-xs text-slate-400">visas/month</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-slate-500">I-485 Pending</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-navy-900">{(cal.total_demand_i485_only ?? 0).toLocaleString()}</div>
                  <p className="text-xs text-slate-400">filed cases</p>
                </CardContent>
              </Card>
              <Card className="border-amber-200 bg-amber-50/30">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-amber-800">Shadow Demand</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-amber-700">{(cal.shadow_demand_ratio ?? 1).toFixed(2)}x</div>
                  <p className="text-xs text-slate-400">I-140 pipeline ratio</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-slate-500">Effective Demand</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-slate-700">{cal.total_demand.toLocaleString()}</div>
                  <p className="text-xs text-slate-400">I-485 + I-140 shadow</p>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Main chart */}
          <Card className="p-6">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-navy-800" />
                FAD Trajectory
              </CardTitle>
              <CardDescription>
                Oppenheim equilibrium forecast with confidence band (70%&ndash;140% of calibrated materialization rate).
                {applyRestrictions && <span className="text-crimson-600 font-medium ml-1">91-country restrictions applied.</span>}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {chartData.length > 0 ? (
                <div className="h-[450px] mt-4">
                  <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
                    <ComposedChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                      <defs>
                        <linearGradient id="confBandOpp" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#002868" stopOpacity={0.12} />
                          <stop offset="95%" stopColor="#002868" stopOpacity={0.02} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis
                        dataKey="label"
                        minTickGap={40}
                        tick={{ fontSize: 11 }}
                      />
                      <YAxis
                        domain={['auto', 'auto']}
                        tickFormatter={formatDateTick}
                        tick={{ fontSize: 11 }}
                        width={80}
                      />
                      <Tooltip
                        labelFormatter={(_label, items) => {
                          const payload = items?.[0]?.payload;
                          return payload?.month ? `Bulletin: ${formatDateDisplay(payload.month)}` : String(_label);
                        }}
                        formatter={(value, name) => {
                          const v = Number(value);
                          if (!v || !isFinite(v)) return ['—', name];
                          return [formatDateTick(v), name];
                        }}
                        contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: 12 }}
                      />
                      <Legend verticalAlign="top" height={36} />

                      {/* Confidence band */}
                      <Area
                        type="monotone"
                        dataKey="fadHigh"
                        stroke="none"
                        fill="url(#confBandOpp)"
                        fillOpacity={1}
                        name="Optimistic"
                        legendType="none"
                        connectNulls={false}
                      />
                      <Area
                        type="monotone"
                        dataKey="fadLow"
                        stroke="none"
                        fill="#ffffff"
                        fillOpacity={1}
                        name="Pessimistic"
                        legendType="none"
                        connectNulls={false}
                      />

                      {/* Predicted FAD */}
                      <Line
                        type="monotone"
                        dataKey="fad"
                        name="Predicted FAD"
                        stroke="#002868"
                        strokeWidth={2.5}
                        dot={{ r: 3, fill: '#002868' }}
                        connectNulls={false}
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <p className="text-slate-400 text-sm py-12 text-center">No trajectory data available.</p>
              )}
            </CardContent>
          </Card>

          {/* How it works */}
          <Card className="bg-slate-50/50 border-slate-200">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Info className="w-4 h-4 text-slate-500" />
                How the Solver Works
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-slate-600 space-y-2">
              <p>
                This models how DOS actually sets the FAD each month: find the priority-date cutoff where
                eligible I-485 demand &times; materialization rate &asymp; monthly visa supply target.
              </p>
              <ol className="list-decimal list-inside space-y-1 text-slate-500">
                <li><strong>Supply:</strong> INA 201/203 cascade computes annual India {data.category} visas ({cal?.annual_supply.toLocaleString()} &divide; 12 = {Math.round(cal?.monthly_supply ?? 0).toLocaleString()}/mo)</li>
                <li><strong>Demand:</strong> USCIS I-485 inventory ({(cal?.total_demand_i485_only ?? 0).toLocaleString()} filed) scaled by shadow ratio ({(cal?.shadow_demand_ratio ?? 1).toFixed(2)}x for I-140 pipeline)</li>
                <li><strong>Calibrate:</strong> Back-solve rate from current VB &rarr; {((cal?.calibrated_rate ?? 0) * 100).toFixed(1)}% materialization</li>
                <li><strong>Solve:</strong> Binary search for FAD where demand(FAD) &times; rate = monthly target</li>
                <li><strong>Bounds:</strong> Vary rate &plusmn;30%/+40% for confidence band</li>
              </ol>
              <p className="text-xs text-slate-400 italic mt-2">
                Shadow demand accounts for {((cal?.shadow_demand_ratio ?? 1) - 1).toFixed(2)}x more applicants from the I-140 pipeline who haven&apos;t filed I-485 yet but will as dates advance.
              </p>
            </CardContent>
          </Card>

          {/* Trajectory table */}
          {data.trajectory && data.trajectory.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <BarChart3 className="w-5 h-5 text-navy-800" />
                  Monthly Trajectory
                </CardTitle>
                <CardDescription>
                  Month-by-month FAD predictions with confidence bounds and remaining FY supply.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left">
                        <th className="pb-3 pr-4 font-semibold text-slate-500">Bulletin Month</th>
                        <th className="pb-3 pr-4 font-semibold text-slate-500">Predicted FAD</th>
                        <th className="pb-3 pr-4 font-semibold text-slate-500">Low (Pessimistic)</th>
                        <th className="pb-3 pr-4 font-semibold text-slate-500">High (Optimistic)</th>
                        <th className="pb-3 pr-4 font-semibold text-slate-500">Demand</th>
                        <th className="pb-3 font-semibold text-slate-500">FY Remaining</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.trajectory.map((pt, i) => (
                        <tr key={i} className={`border-b border-slate-100 hover:bg-slate-50/50 ${
                          i > 0 && data.trajectory[i - 1].fiscal_year !== pt.fiscal_year
                            ? 'border-t-2 border-t-navy-200' : ''
                        }`}>
                          <td className="py-2.5 pr-4 font-medium text-slate-700">
                            {formatDateDisplay(pt.bulletin_month)}
                            {i > 0 && data.trajectory[i - 1].fiscal_year !== pt.fiscal_year && (
                              <Badge variant="outline" className="ml-2 text-[10px]">FY{pt.fiscal_year}</Badge>
                            )}
                          </td>
                          <td className="py-2.5 pr-4 text-navy-900 font-semibold">
                            {pt.is_current ? 'Current' : formatDateDisplay(pt.predicted_fad)}
                          </td>
                          <td className="py-2.5 pr-4 text-slate-500 text-xs">
                            {pt.is_current ? '—' : formatDateDisplay(pt.fad_low)}
                          </td>
                          <td className="py-2.5 pr-4 text-slate-500 text-xs">
                            {pt.is_current ? '—' : formatDateDisplay(pt.fad_high)}
                          </td>
                          <td className="py-2.5 pr-4 text-slate-600">
                            {pt.cumulative_demand.toLocaleString()}
                          </td>
                          <td className="py-2.5 text-slate-500">
                            {(pt.remaining_annual_supply ?? 0).toLocaleString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Methodology */}
          {data.methodology && (
            <p className="text-xs text-slate-400 italic">
              <span className="font-semibold text-slate-500">Methodology:</span> {data.methodology}
            </p>
          )}
        </>
      )}

      {/* Empty state */}
      {!loading && !error && !data && (
        <Card className="p-12 text-center">
          <p className="text-slate-400">Select a category to view Oppenheim prediction data.</p>
        </Card>
      )}
    </div>
  );
}