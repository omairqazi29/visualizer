"use client";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { useWaterfallData } from '@/lib/hooks/useWaterfallData';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, LabelList } from 'recharts';


export default function WaterfallPage() {
  const { data, mode, setMode, error } = useWaterfallData();

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
        <div className="h-10 w-72 animate-pulse rounded bg-slate-200" />
        <div className="h-[520px] animate-pulse rounded-xl border bg-slate-100" />
      </div>
    );
  }

  const fbSavings = data.fb_savings_freeze || 0;
  const eb45Savings = data.eb45_savings_freeze || 0;
  const indiaSupply = data.india_eb1_supply || data.eb1_supply || 0;

  const savingsLabel = mode === 'freeze' ? 'FB Savings (Freeze)' : mode === 'real' ? 'FB Savings (Policy)' : 'FB Savings';
  const chartData = [
    { name: 'EB Base', value: data.eb_base_limit || 140000, fill: '#002868' },
    { name: 'FB Spillover', value: data.fb_spillover_std || 0, fill: '#BF0A30' },
    ...(fbSavings > 0 ? [{ name: savingsLabel, value: fbSavings, fill: '#BF0A30' }] : []),
    { name: 'EB 4/5 Spill+ Savings', value: (data.eb45_spillover_std || 0) + eb45Savings, fill: '#BF0A30' },
    { name: 'Total EB Supply', value: data.total_eb_supply || 0, fill: '#002868', isTotal: true },
    { name: 'India EB-1 Supply', value: indiaSupply, fill: '#003a94', isTotal: true },
  ];

  // For a waterfall, we need to calculate the 'start' and 'end' for each bar
  let current = 0;
  const processedData = chartData.map((item /* , index */) => {
    const isTotal = item.isTotal;
    const val = item.value || 0;
    const start = isTotal ? 0 : current;
    const end = isTotal ? val : current + val;
    if (!isTotal) current += val;
    
    return {
      ...item,
      displayValue: [start, end],
      label: val.toLocaleString()
    };
  });

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-start">
        <div>
          <h2 className="text-3xl font-bold tracking-tight text-navy-900">Visa Flow Waterfall</h2>
          <p className="text-slate-500">From statutory FB limits to final EB-1 supply (INA 201/203 compliant).</p>
        </div>
        <div className="flex items-center gap-2 rounded-lg border bg-slate-50 p-1">
          <button
            onClick={() => setMode('standard')}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-all ${mode === 'standard' ? 'bg-white text-navy-900 shadow-sm' : 'text-slate-600 hover:text-slate-900'}`}
          >
            Standard
          </button>
          <button
            onClick={() => setMode('real')}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-all ${mode === 'real' ? 'bg-navy-900 text-white shadow-sm' : 'text-slate-600 hover:text-slate-900'}`}
          >
            Real Policy
          </button>
          <button
            onClick={() => setMode('freeze')}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-all ${mode === 'freeze' ? 'bg-crimson-600 text-white shadow-sm' : 'text-slate-600 hover:text-slate-900'}`}
          >
            Restriction Scenario
          </button>
        </div>
      </div>

      <Card className="p-6">
        <CardHeader>
          <CardTitle>FY 2026/2027 Spillover Path</CardTitle>
          <CardDescription>Visualizing how unused Family-Based and EB-4/5 visas flow into the India EB-1 pool.</CardDescription>
        </CardHeader>
        <CardContent className="h-[500px] mt-4">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={processedData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" fontSize={12} tickLine={false} axisLine={false} />
              <YAxis tickFormatter={(val) => `${(val / 1000).toFixed(0)}k`} fontSize={12} tickLine={false} axisLine={false} />
              <Tooltip 
                formatter={(value: unknown) => {
                  const v = value as [number, number];
                  return [(v[1] - v[0]).toLocaleString(), 'Visas'];
                }}
                labelStyle={{ fontWeight: 'bold' }}
                contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
              />
              <Bar dataKey="displayValue">
                {/* eslint-disable-next-line @typescript-eslint/no-unused-vars */}
                {processedData.map((entry, _i) => (
                  <Cell key={entry.name} fill={entry.fill} />
                ))}
                <LabelList dataKey="label" position="top" style={{ fontSize: '12px', fontWeight: 'bold', fill: '#475569' }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold">Restriction Savings (FB + EB4/5)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">
              {(fbSavings + eb45Savings).toLocaleString()}
            </div>
            <p className="text-sm text-slate-500 mt-1">Visas reclaimed for EB-1 due to current administrative restrictions.</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold">Standard Spillover</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">
              {((data.fb_spillover_std || 0) + (data.eb45_spillover_std || 0)).toLocaleString()}
            </div>
            <p className="text-sm text-slate-500 mt-1">Normal unused visas flowing from statutory limits.</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
