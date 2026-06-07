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

  // 7–8. Breakdown of Total EB-1: India (base) + Non-India (stacked on top)
  // India EB-1 is what we're tracking — shown as the base portion
  addItem('India\nEB-1', data.india_eb1_supply, bl.india_eb1_supply, '#003a94', true);

  // Non-India stacks on top of India (additive), so together they = Total EB-1
  {
    const indiaEnd = data.india_eb1_supply;
    const blIndiaEnd = bl.india_eb1_supply;
    const nonIndia = data.non_india_eb1;
    const blNonIndia = bl.non_india_eb1;
    items.push({
      name: 'Non-India\nEB-1',
      displayValue: [indiaEnd, indiaEnd + nonIndia],
      baselineEnd: showBoost && (indiaEnd + nonIndia) > (blIndiaEnd + blNonIndia)
        ? blIndiaEnd + blNonIndia
        : indiaEnd + nonIndia,
      hasBoost: showBoost && (indiaEnd + nonIndia) > (blIndiaEnd + blNonIndia),
      baseFill: '#64748b',
      label: nonIndia.toLocaleString(),
    });
    running = 0;
  }

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
          <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
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

      {!isBaseline && (() => {
        // Merge all per-country savings into a single table
        const allCountries = new Set([
          ...Object.keys(data.fb_savings_by_country || {}),
          ...Object.keys(data.eb1_savings_by_country || {}),
          ...Object.keys(data.eb45_savings_by_country || {}),
          ...Object.keys(data.eb23_savings_by_country || {}),
        ]);
        const rows = Array.from(allCountries).map(c => ({
          country: c,
          fb: (data.fb_savings_by_country || {})[c] || 0,
          eb1: (data.eb1_savings_by_country || {})[c] || 0,
          eb45: (data.eb45_savings_by_country || {})[c] || 0,
          eb23: (data.eb23_savings_by_country || {})[c] || 0,
          total: ((data.fb_savings_by_country || {})[c] || 0) +
                 ((data.eb1_savings_by_country || {})[c] || 0) +
                 ((data.eb45_savings_by_country || {})[c] || 0) +
                 ((data.eb23_savings_by_country || {})[c] || 0),
        })).filter(r => r.total > 0).sort((a, b) => b.total - a.total);

        if (rows.length === 0) return null;

        const top10 = rows.slice(0, 10);
        const remaining = rows.slice(10);
        const remainingTotal = remaining.reduce((s, r) => s + r.total, 0);

        return (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Country-Level DOS IV Savings Breakdown</CardTitle>
              <CardDescription>
                Per-country visa savings from the 91-country restrictions (Proclamation ban + DOS IV pause).
                Shows which restricted countries contribute the most unused visas that spill over to India EB-1.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-left">
                      <th className="py-2 pr-4 font-semibold text-slate-700">Country</th>
                      <th className="py-2 px-3 font-semibold text-slate-700 text-right">FB</th>
                      <th className="py-2 px-3 font-semibold text-slate-700 text-right">EB-1</th>
                      <th className="py-2 px-3 font-semibold text-slate-700 text-right">EB-4/5</th>
                      <th className="py-2 px-3 font-semibold text-slate-700 text-right">EB-2/3</th>
                      <th className="py-2 px-3 font-semibold text-slate-700 text-right">Total</th>
                      <th className="py-2 pl-3 font-semibold text-slate-700 text-right">Share</th>
                    </tr>
                  </thead>
                  <tbody>
                    {top10.map((r, i) => (
                      <tr key={r.country} className={`border-b border-slate-100 ${i === 0 ? 'bg-crimson-50/50' : ''}`}>
                        <td className="py-1.5 pr-4 font-medium text-slate-800">{r.country}</td>
                        <td className="py-1.5 px-3 text-right tabular-nums text-slate-600">{r.fb > 0 ? r.fb.toLocaleString() : '—'}</td>
                        <td className="py-1.5 px-3 text-right tabular-nums text-slate-600">{r.eb1 > 0 ? r.eb1.toLocaleString() : '—'}</td>
                        <td className="py-1.5 px-3 text-right tabular-nums text-slate-600">{r.eb45 > 0 ? r.eb45.toLocaleString() : '—'}</td>
                        <td className="py-1.5 px-3 text-right tabular-nums text-slate-600">{r.eb23 > 0 ? r.eb23.toLocaleString() : '—'}</td>
                        <td className="py-1.5 px-3 text-right tabular-nums font-semibold text-crimson-700">{r.total.toLocaleString()}</td>
                        <td className="py-1.5 pl-3 text-right tabular-nums text-slate-500">{totalSavings > 0 ? `${((r.total / totalSavings) * 100).toFixed(1)}%` : '—'}</td>
                      </tr>
                    ))}
                    {remaining.length > 0 && (
                      <tr className="border-b border-slate-100 bg-slate-50/50">
                        <td className="py-1.5 pr-4 font-medium text-slate-500 italic">Other {remaining.length} countries</td>
                        <td className="py-1.5 px-3 text-right tabular-nums text-slate-400">{remaining.reduce((s, r) => s + r.fb, 0).toLocaleString()}</td>
                        <td className="py-1.5 px-3 text-right tabular-nums text-slate-400">{remaining.reduce((s, r) => s + r.eb1, 0).toLocaleString()}</td>
                        <td className="py-1.5 px-3 text-right tabular-nums text-slate-400">{remaining.reduce((s, r) => s + r.eb45, 0).toLocaleString()}</td>
                        <td className="py-1.5 px-3 text-right tabular-nums text-slate-400">{remaining.reduce((s, r) => s + r.eb23, 0).toLocaleString()}</td>
                        <td className="py-1.5 px-3 text-right tabular-nums font-semibold text-slate-500">{remainingTotal.toLocaleString()}</td>
                        <td className="py-1.5 pl-3 text-right tabular-nums text-slate-400">{totalSavings > 0 ? `${((remainingTotal / totalSavings) * 100).toFixed(1)}%` : '—'}</td>
                      </tr>
                    )}
                  </tbody>
                  <tfoot>
                    <tr className="border-t-2 border-slate-300">
                      <td className="py-2 pr-4 font-bold text-slate-800">Total</td>
                      <td className="py-2 px-3 text-right tabular-nums font-bold text-slate-700">{(data.fb_savings || 0).toLocaleString()}</td>
                      <td className="py-2 px-3 text-right tabular-nums font-bold text-slate-700">{(data.eb1_savings || 0).toLocaleString()}</td>
                      <td className="py-2 px-3 text-right tabular-nums font-bold text-slate-700">{(data.eb45_savings || 0).toLocaleString()}</td>
                      <td className="py-2 px-3 text-right tabular-nums font-bold text-slate-700">{(data.eb23_savings || 0).toLocaleString()}</td>
                      <td className="py-2 px-3 text-right tabular-nums font-bold text-crimson-700">{totalSavings.toLocaleString()}</td>
                      <td className="py-2 pl-3 text-right tabular-nums font-bold text-slate-700">100%</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </CardContent>
          </Card>
        );
      })()}

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
