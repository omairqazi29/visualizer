"use client";

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { getWaterfallData } from '@/lib/api';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, LabelList } from 'recharts';

export default function WaterfallPage() {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    getWaterfallData().then(setData);
  }, []);

  if (!data) return <div>Loading visualization...</div>;

  const chartData = [
    { name: 'EB Base', value: data.eb_base_limit, fill: '#002868' },
    { name: 'FB Spillover', value: data.fb_spillover, fill: '#BF0A30' },
    { name: 'Savings', value: data.redistribution_savings, fill: '#BF0A30' },
    { name: 'Total EB', value: data.total_eb_supply, fill: '#002868', isTotal: true },
    { name: 'EB-1 (28.6%)', value: data.eb1_supply, fill: '#003a94', isTotal: true },
  ];

  // For a waterfall, we need to calculate the 'start' and 'end' for each bar
  let current = 0;
  const processedData = chartData.map((item, index) => {
    const isTotal = item.isTotal;
    const start = isTotal ? 0 : current;
    const end = isTotal ? item.value : current + item.value;
    if (!isTotal) current += item.value;
    
    return {
      ...item,
      displayValue: [start, end],
      label: item.value.toLocaleString()
    };
  });

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-navy-900">Visa Flow Waterfall</h2>
        <p className="text-slate-500">From statutory FB limits to final EB-1 supply (INA 201/203 compliant).</p>
      </div>

      <Card className="p-6">
        <CardHeader>
          <CardTitle>FY 2026/2027 Spillover Path</CardTitle>
          <CardDescription>Visualizing how unused Family-Based visas and country-cap savings flow into Employment-Based categories.</CardDescription>
        </CardHeader>
        <CardContent className="h-[500px] mt-4">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={processedData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" />
              <YAxis tickFormatter={(val) => `${(val / 1000).toFixed(0)}k`} />
              <Tooltip 
                formatter={(value: any) => value[1] - value[0]}
                labelStyle={{ fontWeight: 'bold' }}
              />
              <Bar dataKey="displayValue">
                {processedData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.fill} />
                ))}
                <LabelList dataKey="label" position="top" />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold">Redistribution Savings</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">{data.redistribution_savings?.toLocaleString()}</div>
            <p className="text-sm text-slate-500 mt-1">Visas reclaimed from restricted countries under the 75-country freeze logic.</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold">FB Spillover</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">{data.fb_spillover?.toLocaleString()}</div>
            <p className="text-sm text-slate-500 mt-1">Unused Family-Based visas from the 226,000 statutory floor.</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
