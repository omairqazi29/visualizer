"use client";

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { getWaterfallData, WaterfallData } from '@/lib/api';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, LabelList } from 'recharts';


export default function WaterfallPage() {
  const [data, setData] = useState<WaterfallData | null>(null);
  const [baselineData, setBaselineData] = useState<WaterfallData | null>(null);
  const [mode, setMode] = useState<'current' | 'baseline'>('current');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const applyReal = mode === 'current';
    Promise.all([
      getWaterfallData(false, applyReal),
      getWaterfallData(false, false),       // always fetch baseline for comparison
    ])
      .then(([d, bl]) => { setData(d); setBaselineData(bl); })
      .catch((e: unknown) => {
        const err = e as { message?: string };
        setError(err?.message || 'Failed to load waterfall data');
      });
  }, [mode]);

  if (error) {
    return (
      <div className="rounded-lg border border-crimson-200 bg-crimson-50 p-4 text-crimson-700">
        {error}
      </div>
    );
  }
  if (!data || !baselineData) {
    return (
      <div className="space-y-6">
        <div className="h-10 w-72 animate-pulse rounded bg-slate-200" />
        <div className="h-[520px] animate-pulse rounded-xl border bg-slate-100" />
      </div>
    );
  }

  const isBaseline = mode === 'baseline';

  // Full INA cascade waterfall: Total EB → EB-1 → India / Non-India
  interface ChartItem {
    name: string;
    value: number;
    fill: string;
    isTotal?: boolean;
    isSubtract?: boolean;
  }
  const chartData: ChartItem[] = [
    { name: 'EB Base\nLimit', value: data.eb_base_limit, fill: '#002868' },
    { name: 'FB →\nEB Spill', value: data.fb_spillover, fill: '#1e40af' },
    { name: 'Total EB\nPool', value: data.total_eb_pool, fill: '#002868', isTotal: true },
    { name: 'EB-1\n(28.6%)', value: data.eb1_from_pool, fill: '#1e40af', isTotal: true },
    ...(data.eb45_spillover > 0 ? [{ name: 'EB4/5 →\nEB-1', value: data.eb45_spillover, fill: '#BF0A30' }] : []),
    { name: 'Total\nEB-1', value: data.total_eb1, fill: '#002868', isTotal: true },
    { name: 'India\nEB-1', value: data.india_eb1_supply, fill: '#003a94', isTotal: true },
    { name: 'Non-India\nEB-1', value: data.non_india_eb1, fill: '#64748b', isTotal: true },
  ];

  // Compute waterfall start/end positions
  let running = 0;
  const processedData = chartData.map((item) => {
    const val = Math.abs(item.value || 0);
    let start: number, end: number;

    if (item.isTotal) {
      start = 0;
      end = val;
      running = 0;  // reset for next additive section
    } else if (item.isSubtract) {
      start = running - val;
      end = running;
      running -= val;
    } else {
      start = running;
      end = running + val;
      running += val;
    }

    return {
      ...item,
      displayValue: [start, end],
      label: val.toLocaleString(),
    };
  });

  const totalSavings = (data.fb_savings || 0) + (data.eb1_savings || 0) + (data.eb45_savings || 0) + (data.eb23_savings || 0);
  const indiaAdditional = (data.india_eb1_supply || 0) - (data.india_eb1_baseline || 0);

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-start">
        <div>
          <h2 className="text-3xl font-bold tracking-tight text-navy-900">Visa Supply Waterfall</h2>
          <p className="text-slate-500">Full INA 201/203 cascade: Total EB → EB-1 → India vs Non-India.</p>
        </div>
        <div className="flex items-center gap-2 rounded-lg border bg-slate-50 p-1">
          <button
            onClick={() => setMode('baseline')}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-all ${mode === 'baseline' ? 'bg-white text-navy-900 shadow-sm' : 'text-slate-600 hover:text-slate-900'}`}
          >
            Baseline
          </button>
          <button
            onClick={() => setMode('current')}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-all ${mode === 'current' ? 'bg-crimson-600 text-white shadow-sm' : 'text-slate-600 hover:text-slate-900'}`}
          >
            Current Policy (91 countries)
          </button>
        </div>
      </div>

      <Card className="p-6">
        <CardHeader>
          <CardTitle>{isBaseline ? 'Baseline INA Cascade' : 'Current Policy Cascade (91-Country Restrictions)'}</CardTitle>
          <CardDescription>
            {isBaseline
              ? 'Standard INA flow: EB base + FB spillover → 28.6% to EB-1 → India gets its share.'
              : 'Restricted countries\u2019 unused FB/EB visas expand the pool. India gets 80% of additional EB-1 (shared with China).'}
          </CardDescription>
        </CardHeader>
        <CardContent className="h-[500px] mt-4">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={processedData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" fontSize={11} tickLine={false} axisLine={false} interval={0} />
              <YAxis tickFormatter={(val: number) => `${(val / 1000).toFixed(0)}k`} fontSize={12} tickLine={false} axisLine={false} />
              <Tooltip
                formatter={(value: unknown) => {
                  const v = value as [number, number];
                  return [Math.abs(v[1] - v[0]).toLocaleString(), 'Visas'];
                }}
                labelStyle={{ fontWeight: 'bold' }}
                contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
              />
              <Bar dataKey="displayValue">
                {processedData.map((entry) => (
                  <Cell key={entry.name} fill={entry.fill} />
                ))}
                <LabelList dataKey="label" position="top" style={{ fontSize: '11px', fontWeight: 'bold', fill: '#475569' }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">Total EB-1 Worldwide</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">{(data.total_eb1 || 0).toLocaleString()}</div>
            <p className="text-xs text-slate-500 mt-1">
              {isBaseline
                ? '28.6% of EB pool. EB4/5 oversubscribed — no spillover to EB-1.'
                : `vs baseline ${(baselineData.total_eb1 || 0).toLocaleString()} (+${((data.total_eb1 || 0) - (baselineData.total_eb1 || 0)).toLocaleString()})`}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">India EB-1</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">{(data.india_eb1_supply || 0).toLocaleString()}</div>
            <p className="text-xs text-slate-500 mt-1">
              {isBaseline
                ? 'FY2024 actual (consular + AOS). India is ~13% of EB-1.'
                : `Baseline ${(data.india_eb1_baseline || 0).toLocaleString()} + ${indiaAdditional.toLocaleString()} from restrictions`}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">Non-India EB-1</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">{(data.non_india_eb1 || 0).toLocaleString()}</div>
            <p className="text-xs text-slate-500 mt-1">China + Rest of World (includes ~20% of additional to China)</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">Restriction Savings (All EB)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">{isBaseline ? '0' : totalSavings.toLocaleString()}</div>
            <p className="text-xs text-slate-500 mt-1">
              {isBaseline
                ? 'No restrictions in baseline.'
                : `FB: ${(data.fb_savings || 0).toLocaleString()} | EB-1: ${(data.eb1_savings || 0).toLocaleString()} | EB4/5: ${(data.eb45_savings || 0).toLocaleString()} | EB2/3: ${(data.eb23_savings || 0).toLocaleString()}`}
            </p>
          </CardContent>
        </Card>
      </div>

      {!isBaseline && (
        <p className="text-xs text-slate-400 italic">
          DOS monthly data captures consular IV issuances only (not domestic AOS). EB categories are AOS-heavy, so direct EB savings from restrictions are small.
          The main India EB-1 benefit comes through FB savings (consular-heavy) expanding the total EB pool. India receives 80% of additional EB-1 based on relative I-485 backlogs (India ~48k vs China ~10k).
        </p>
      )}
    </div>
  );
}
