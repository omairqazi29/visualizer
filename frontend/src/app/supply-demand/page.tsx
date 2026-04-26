"use client";

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { getSupplyDemandData, SupplyDemandData } from '@/lib/api';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';

export default function SupplyDemandPage() {
  const [standardData, setStandardData] = useState<SupplyDemandData | null>(null);
  const [freezeData, setFreezeData] = useState<SupplyDemandData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      getSupplyDemandData(false),
      getSupplyDemandData(true)
    ])
      .then(([std, frz]) => {
        setStandardData(std);
        setFreezeData(frz);
      })
      .catch((e: unknown) => {
        const err = e as { message?: string };
        setError(err?.message || 'Failed to load supply/demand data');
      });
  }, []);

  if (error) return <div className="text-crimson-600">Error: {error}</div>;
  if (!standardData || !freezeData) return <div>Loading comparison...</div>;

  // Combine trajectories for the chart
  const projection = standardData.trajectory.map((t, idx: number) => ({
    date: t.date,
    dateLabel: new Date(t.date).toLocaleDateString(undefined, { month: 'short', year: '2-digit' }),
    standardBacklog: t.backlog,
    freezeBacklog: freezeData.trajectory[idx]?.backlog || 0
  }));

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-navy-900">Backlog Comparison</h2>
        <p className="text-slate-500">Comparing Standard INA Flow vs. 75-Country Freeze Impact.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">Standard Clearance</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-slate-400">
              {new Date(standardData.clearance_date).toLocaleDateString(undefined, { month: 'short', year: 'numeric' })}
            </div>
          </CardContent>
        </Card>
        <Card className="border-crimson-200 bg-crimson-50/30">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-crimson-800">Restriction Clearance</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-crimson-600">
              {new Date(freezeData.clearance_date).toLocaleDateString(undefined, { month: 'short', year: 'numeric' })}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-navy-700">Acceleration</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">
              {Math.round((standardData.months_to_clear || 0) - (freezeData.months_to_clear || 0))} Months Faster
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="p-6">
        <CardHeader>
          <CardTitle>The Restriction Delta</CardTitle>
          <CardDescription>How travel bans and 75-country freezes accelerate India EB-1 backlog clearance.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[450px] mt-4">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={projection}>
                <defs>
                  <linearGradient id="colorStd" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#94a3b8" stopOpacity={0.1}/>
                    <stop offset="95%" stopColor="#94a3b8" stopOpacity={0}/>
                  </linearGradient>
                  <linearGradient id="colorFrz" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#BF0A30" stopOpacity={0.1}/>
                    <stop offset="95%" stopColor="#BF0A30" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="dateLabel" minTickGap={30} />
                <YAxis tickFormatter={(val) => `${(val / 1000).toFixed(0)}k`} />
                <Tooltip 
                  labelFormatter={(label, items) => items[0]?.payload?.date}
                  contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
                />
                <Legend verticalAlign="top" height={36}/>
                <Area 
                  type="monotone" 
                  dataKey="standardBacklog" 
                  name="Standard INA Flow"
                  stroke="#94a3b8" 
                  strokeWidth={2}
                  fillOpacity={1} 
                  fill="url(#colorStd)" 
                />
                <Area 
                  type="monotone" 
                  dataKey="freezeBacklog" 
                  name="Restriction Mode (Freeze)"
                  stroke="#BF0A30" 
                  strokeWidth={3}
                  fillOpacity={1} 
                  fill="url(#colorFrz)" 
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
