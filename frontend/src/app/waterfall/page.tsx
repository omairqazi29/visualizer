"use client";

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { getWaterfallData } from '@/lib/api';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, LabelList } from 'recharts';
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export default function WaterfallPage() {
  const [data, setData] = useState<any>(null);
  const [applyFreeze, setApplyFreeze] = useState(false);

  useEffect(() => {
    getWaterfallData(applyFreeze).then(setData);
  }, [applyFreeze]);

  if (!data) return <div>Loading visualization...</div>;

  const chartData = [
    { name: 'EB Base', value: data.eb_base_limit || 140000, fill: '#002868' },
    { name: 'FB Spillover', value: data.fb_spillover_std || 0, fill: '#BF0A30' },
    { name: 'FB Savings', value: data.fb_savings_freeze || 0, fill: '#BF0A30' },
    { name: 'EB 4/5 Spill', value: (data.eb45_spillover_std || 0) + (data.eb45_savings_freeze || 0), fill: '#BF0A30' },
    { name: 'Total EB', value: data.total_eb_supply || 0, fill: '#002868', isTotal: true },
    { name: 'India EB-1', value: data.eb1_supply || 0, fill: '#003a94', isTotal: true },
  ];

  // For a waterfall, we need to calculate the 'start' and 'end' for each bar
  let current = 0;
  const processedData = chartData.map((item, index) => {
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
        <div className="flex flex-col items-end gap-2">
          <Button 
            variant={applyFreeze ? "destructive" : "outline"} 
            onClick={() => setApplyFreeze(!applyFreeze)}
          >
            {applyFreeze ? "Disable Trump Effect" : "Apply Trump Effect"}
          </Button>
          <Badge variant={applyFreeze ? "default" : "secondary"}>
            {applyFreeze ? "Restriction Mode" : "Standard INA Flow"}
          </Badge>
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
                formatter={(value: any) => (value[1] - value[0]).toLocaleString()}
                labelStyle={{ fontWeight: 'bold' }}
              />
              <Bar dataKey="displayValue">
                {processedData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.fill} />
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
              {((data.fb_savings_freeze || 0) + (data.eb45_savings_freeze || 0)).toLocaleString()}
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
