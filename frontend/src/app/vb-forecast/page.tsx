"use client";

import { useEffect, useState, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getVBForecast, VBForecastData } from '@/lib/api';
import {
  ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { LineChart, TrendingUp, AlertTriangle, BarChart3 } from 'lucide-react';

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

function formatDateDisplay(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
}

function safeParse(dateStr: string | null | undefined): number | null {
  if (!dateStr) return null;
  const t = new Date(dateStr).getTime();
  return isFinite(t) ? t : null;
}

export default function VBForecastPage() {
  const [category, setCategory] = useState<string>('EB-1');
  const [applyRestrictions, setApplyRestrictions] = useState(false);
  const [data, setData] = useState<VBForecastData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getVBForecast(category, 24, applyRestrictions)
      .then(setData)
      .catch((err: unknown) => {
        const e = err as { response?: { data?: { detail?: string } }; message?: string };
        setError(e?.response?.data?.detail || e?.message || 'Failed to load VB forecast');
      })
      .finally(() => setLoading(false));
  }, [category, applyRestrictions]);

  const chartData = useMemo(() => {
    if (!data) return [];
    const historical = (data.historical || [])
      .filter(h => h.fad)
      .map(h => ({
        month: h.bulletin_month,
        label: formatMonthLabel(h.bulletin_month),
        actualFad: safeParse(h.fad),
        actualDof: safeParse(h.dof),
        forecastFad: null as number | null,
        forecastDof: null as number | null,
        confidenceLow: null as number | null,
        confidenceHigh: null as number | null,
      }));

    const forecast = (data.forecast || []).map(f => ({
      month: f.bulletin_month,
      label: formatMonthLabel(f.bulletin_month),
      actualFad: null as number | null,
      actualDof: null as number | null,
      forecastFad: safeParse(f.predicted_fad),
      forecastDof: safeParse(f.predicted_dof),
      confidenceLow: safeParse(f.fad_confidence_low),
      confidenceHigh: safeParse(f.fad_confidence_high),
    }));

    // Bridge: duplicate the last historical point into forecast so lines connect
    if (historical.length > 0 && forecast.length > 0) {
      const last = historical[historical.length - 1];
      forecast[0] = {
        ...forecast[0],
        actualFad: last.actualFad,
        actualDof: last.actualDof,
      };
    }

    return [...historical, ...forecast];
  }, [data]);

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
          {Array.from({ length: 3 }).map((_, i) => (
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
          <LineChart className="w-8 h-8 text-navy-800" />
          Visa Bulletin Forecast
        </h2>
        <p className="text-slate-500 mt-1">
          Predicts future <span className="font-semibold">Final Action Date (FAD)</span> and{' '}
          <span className="font-semibold">Date of Filing (DOF)</span> movement month by month for India EB categories.
        </p>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-4">
        {/* Category buttons */}
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
          {/* Latest actual */}
          {data.latest_actual && (
            <Card className="border-slate-200 bg-slate-50/50">
              <CardContent className="pt-5 pb-4">
                <div className="flex flex-wrap items-center gap-6 text-sm">
                  <div>
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Latest Bulletin</span>
                    <p className="font-semibold text-slate-700">{formatDateDisplay(data.latest_actual.bulletin_month)}</p>
                  </div>
                  <div>
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Current FAD</span>
                    <p className="font-semibold text-navy-900">{formatDateDisplay(data.latest_actual.fad)}</p>
                  </div>
                  {data.latest_actual.dof && (
                    <div>
                      <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Current DOF</span>
                      <p className="font-semibold text-emerald-700">{formatDateDisplay(data.latest_actual.dof)}</p>
                    </div>
                  )}
                  <Badge variant="outline" className="text-xs">{data.category} &mdash; {data.country}</Badge>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Main chart */}
          <Card className="p-6">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-navy-800" />
                FAD &amp; DOF Projection
              </CardTitle>
              <CardDescription>
                Historical dates (solid) and forecast (dashed) with confidence band.{' '}
                {applyRestrictions && <span className="text-crimson-600 font-medium">91-country restrictions applied.</span>}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {chartData.length > 0 ? (
                <div className="h-[450px] mt-4">
                  <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
                    <ComposedChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                      <defs>
                        <linearGradient id="confBand" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.15} />
                          <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.03} />
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
                          return payload?.month ? formatDateDisplay(payload.month) : String(_label);
                        }}
                        formatter={(value, name) => {
                          const v = Number(value);
                          if (!v || !isFinite(v)) return ['-', name];
                          return [formatDateTick(v), name];
                        }}
                        contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: 12 }}
                      />
                      <Legend verticalAlign="top" height={36} />

                      {/* Confidence band */}
                      <Area
                        type="monotone"
                        dataKey="confidenceHigh"
                        stroke="none"
                        fill="url(#confBand)"
                        fillOpacity={1}
                        name="Confidence High"
                        legendType="none"
                        connectNulls={false}
                      />
                      <Area
                        type="monotone"
                        dataKey="confidenceLow"
                        stroke="none"
                        fill="#ffffff"
                        fillOpacity={1}
                        name="Confidence Low"
                        legendType="none"
                        connectNulls={false}
                      />

                      {/* Historical FAD */}
                      <Line
                        type="monotone"
                        dataKey="actualFad"
                        name="Historical FAD"
                        stroke="#3b82f6"
                        strokeWidth={2.5}
                        dot={false}
                        connectNulls={false}
                      />
                      {/* Forecast FAD */}
                      <Line
                        type="monotone"
                        dataKey="forecastFad"
                        name="Forecast FAD"
                        stroke="#002868"
                        strokeWidth={2.5}
                        strokeDasharray="6 3"
                        dot={false}
                        connectNulls={false}
                      />
                      {/* Historical DOF */}
                      <Line
                        type="monotone"
                        dataKey="actualDof"
                        name="Historical DOF"
                        stroke="#22c55e"
                        strokeWidth={2}
                        dot={false}
                        connectNulls={false}
                      />
                      {/* Forecast DOF */}
                      <Line
                        type="monotone"
                        dataKey="forecastDof"
                        name="Forecast DOF"
                        stroke="#16a34a"
                        strokeWidth={2}
                        strokeDasharray="6 3"
                        dot={false}
                        connectNulls={false}
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <p className="text-slate-400 text-sm py-12 text-center">No chart data available.</p>
              )}
            </CardContent>
          </Card>

          {/* Stats cards */}
          {data.stats && (
            <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-6">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-slate-500">Avg Advancement</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-navy-900">{data.stats.recent_avg.toFixed(1)}</div>
                  <p className="text-xs text-slate-400">days/month (recent)</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-slate-500">Median Advancement</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-navy-900">{data.stats.recent_median.toFixed(1)}</div>
                  <p className="text-xs text-slate-400">days/month (recent)</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-slate-500">Data Points</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-slate-700">{data.stats.n_datapoints}</div>
                  <p className="text-xs text-slate-400">months of history</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-slate-500">Retrogressions</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-crimson-600">{data.stats.retrogression_count}</div>
                  <p className="text-xs text-slate-400">months with backward moves</p>
                </CardContent>
              </Card>
              {applyRestrictions && (
                <Card className="border-crimson-200 bg-crimson-50/30">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium text-crimson-800">Supply Factor</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold text-crimson-600">{data.supply_factor.toFixed(2)}x</div>
                    <p className="text-xs text-slate-400">restriction multiplier</p>
                  </CardContent>
                </Card>
              )}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-slate-500">DOF-FAD Gap</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-emerald-700">{data.dof_gap_months.toFixed(1)}</div>
                  <p className="text-xs text-slate-400">months ahead of FAD</p>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Forecast table */}
          {data.forecast && data.forecast.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <BarChart3 className="w-5 h-5 text-navy-800" />
                  Monthly Forecast
                </CardTitle>
                <CardDescription>
                  Predicted FAD, DOF, and confidence range for the next {data.forecast.length} months.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left">
                        <th className="pb-3 pr-4 font-semibold text-slate-500">Bulletin Month</th>
                        <th className="pb-3 pr-4 font-semibold text-slate-500">Predicted FAD</th>
                        <th className="pb-3 pr-4 font-semibold text-slate-500">Predicted DOF</th>
                        <th className="pb-3 font-semibold text-slate-500">Confidence Range</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.forecast.map((f, i) => (
                        <tr key={i} className="border-b border-slate-100 hover:bg-slate-50/50">
                          <td className="py-2.5 pr-4 font-medium text-slate-700">
                            {formatDateDisplay(f.bulletin_month)}
                          </td>
                          <td className="py-2.5 pr-4 text-navy-900 font-semibold">
                            {formatDateDisplay(f.predicted_fad)}
                          </td>
                          <td className="py-2.5 pr-4 text-emerald-700">
                            {f.predicted_dof ? formatDateDisplay(f.predicted_dof) : <span className="text-slate-300">&mdash;</span>}
                          </td>
                          <td className="py-2.5 text-slate-500 text-xs">
                            {formatDateDisplay(f.fad_confidence_low)} &ndash; {formatDateDisplay(f.fad_confidence_high)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Methodology note */}
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
          <p className="text-slate-400">Select a category to view forecast data.</p>
        </Card>
      )}
    </div>
  );
}