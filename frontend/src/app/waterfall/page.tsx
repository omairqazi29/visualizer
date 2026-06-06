"use client";

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { getWaterfallData, WaterfallData } from '@/lib/api';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LabelList } from 'recharts';

const BOOST_COLOR = '#BF0A30';  // crimson red for restriction delta

/** Custom bar shape that splits a range bar into base (blue) + boost (red) portions. */
const SplitBar = (props: Record<string, unknown>) => {
  const { x: px, y: py, width: pw, height: ph, payload } = props as {
    x: number; y: number; width: number; height: number;
    payload: { baseFill: string; hasBoost: boolean; displayValue: [number, number]; baselineEnd: number };
  };
  const h = Math.abs(ph);
  if (!h) return null;

  if (!payload.hasBoost) {
    return <rect x={px} y={py} width={pw} height={h} fill={payload.baseFill} rx={2} />;
  }

  const [rangeStart, rangeEnd] = payload.displayValue;
  const totalSpan = rangeEnd - rangeStart;
  if (totalSpan <= 0) {
    return <rect x={px} y={py} width={pw} height={h} fill={payload.baseFill} rx={2} />;
  }

  const baseSpan = Math.max(0, payload.baselineEnd - rangeStart);
  const baseFraction = baseSpan / totalSpan;
  const baseH = baseFraction * h;
  const boostH = h - baseH;

  return (
    <g>
      {baseH > 0.5 && (
        <rect x={px} y={py + boostH} width={pw} height={baseH} fill={payload.baseFill} rx={baseH > 4 ? 2 : 0} />
      )}
      {boostH > 0.5 && (
        <rect x={px} y={py} width={pw} height={boostH} fill={BOOST_COLOR} rx={boostH > 4 ? 2 : 0} />
      )}
    </g>
  );
};


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
  const bl = baselineData;
  const showBoost = !isBaseline;

  // Build waterfall items with baseline split points for red highlighting
  interface WaterfallItem {
    name: string;
    displayValue: [number, number];
    baselineEnd: number;     // data-unit Y where baseline portion ends (red starts above)
    hasBoost: boolean;
    baseFill: string;
    label: string;
    isTotal?: boolean;
  }

  const items: WaterfallItem[] = [];
  let running = 0;

  const addItem = (
    name: string, value: number, baselineValue: number,
    fill: string, isTotal: boolean
  ) => {
    const val = Math.abs(value || 0);
    const blVal = Math.abs(baselineValue || 0);
    let start: number, end: number;

    if (isTotal) {
      start = 0;
      end = val;
      running = 0;
    } else {
      start = running;
      end = running + val;
      running += val;
    }

    const baseEnd = isTotal
      ? Math.min(blVal, end)
      : Math.min(start + blVal, end);

    items.push({
      name,
      displayValue: [start, end],
      baselineEnd: showBoost && end > baseEnd ? baseEnd : end,
      hasBoost: showBoost && end > baseEnd,
      baseFill: fill,
      label: val.toLocaleString(),
      isTotal,
    });
  };

  // 1. EB Base Limit (same in both scenarios)
  addItem('EB Base\nLimit', data.eb_base_limit, bl.eb_base_limit, '#002868', false);

  // 2. FB → EB Spillover (restriction savings inflate this)
  addItem('FB →\nEB Spill', data.fb_spillover, bl.fb_spillover, '#1e40af', false);

  // 3. Total EB Pool
  addItem('Total EB\nPool', data.total_eb_pool, bl.total_eb_pool, '#002868', true);

  // 4. EB-1 (28.6%)
  addItem('EB-1\n(28.6%)', data.eb1_from_pool, bl.eb1_from_pool, '#1e40af', true);

  // 5. EB4/5 → EB-1 (entirely restriction benefit — baseline is 0)
  if (data.eb45_spillover > 0) {
    // Additive bar stacking on top of EB-1
    const start = data.eb1_from_pool;
    const end = start + data.eb45_spillover;
    const blSpill = bl.eb45_spillover || 0;
    items.push({
      name: 'EB4/5 →\nEB-1',
      displayValue: [start, end],
      baselineEnd: showBoost ? start + blSpill : end,
      hasBoost: showBoost && data.eb45_spillover > blSpill,
      baseFill: '#1e40af',
      label: data.eb45_spillover.toLocaleString(),
    });
    running = 0; // reset for next total
  }

  // 6. Total EB-1
  addItem('Total\nEB-1', data.total_eb1, bl.total_eb1, '#002868', true);

  // 7. Non-India EB-1 (the majority — shown first as the larger portion)
  addItem('Non-India\nEB-1', data.non_india_eb1, bl.non_india_eb1, '#64748b', true);

  // 8. India EB-1 (the specific carve-out we're tracking)
  addItem('India\nEB-1', data.india_eb1_supply, bl.india_eb1_supply, '#003a94', true);

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
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>{isBaseline ? 'Baseline INA Cascade' : 'Current Policy Cascade (91-Country Restrictions)'}</CardTitle>
              <CardDescription>
                {isBaseline
                  ? 'Standard INA flow: EB base + FB spillover \u2192 28.6% to EB-1 \u2192 India gets its share.'
                  : `Restricted countries\u2019 unused FB/EB visas expand the pool. India gets ${Math.round((data.india_oversubscribed_share || 0.84) * 100)}% of additional EB-1 (shared with China).`}
              </CardDescription>
            </div>
            {!isBaseline && (
              <div className="flex items-center gap-4 text-xs font-medium shrink-0 ml-4">
                <span className="flex items-center gap-1.5">
                  <span className="inline-block w-3 h-3 rounded-sm" style={{ background: '#002868' }} />
                  Baseline
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block w-3 h-3 rounded-sm" style={{ background: BOOST_COLOR }} />
                  Restriction Boost
                </span>
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent className="h-[500px] mt-4">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={items} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
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
              <Bar dataKey="displayValue" shape={<SplitBar />}>
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
                ? '28.6% of EB pool. EB4/5 oversubscribed \u2014 no spillover to EB-1.'
                : <>vs baseline {(bl.total_eb1 || 0).toLocaleString()} (<span className="text-crimson-600 font-semibold">+{((data.total_eb1 || 0) - (bl.total_eb1 || 0)).toLocaleString()}</span>)</>}
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
                ? `FY2024 actual (consular + AOS). India is ~${Math.round(((data.india_eb1_baseline || 6952) / (bl.total_eb1 || 47462)) * 100)}% of EB-1.`
                : <>Baseline {(data.india_eb1_baseline || 0).toLocaleString()} + <span className="text-crimson-600 font-semibold">+{indiaAdditional.toLocaleString()}</span> from restrictions</>}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">Non-India EB-1</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">{(data.non_india_eb1 || 0).toLocaleString()}</div>
            <p className="text-xs text-slate-500 mt-1">China + Rest of World (includes ~{Math.round((1 - (data.india_oversubscribed_share || 0.84)) * 100)}% of additional to China)</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">Restriction Savings (All EB)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-crimson-600">{isBaseline ? '0' : `+${totalSavings.toLocaleString()}`}</div>
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
          <span className="font-semibold text-crimson-500">Red portions</span> show the restriction boost vs baseline.
          DOS monthly data captures consular IV issuances only (not domestic AOS). EB categories are AOS-heavy, so direct EB savings are small.
          The main India EB-1 benefit comes through FB savings (consular-heavy) expanding the total EB pool. India receives {Math.round((data.india_oversubscribed_share || 0.84) * 100)}% of additional EB-1 based on relative I-485 backlogs (computed from USCIS inventory data).
        </p>
      )}
    </div>
  );
}
