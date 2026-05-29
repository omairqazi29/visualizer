"use client";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { useSupplyDemandData } from '@/lib/hooks/useSupplyDemandData';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';

export default function SupplyDemandPage() {
  const { standardData, realData, freezeData, error } = useSupplyDemandData();

  if (error) {
    return (
      <div className="rounded-lg border border-crimson-200 bg-crimson-50 p-4 text-crimson-700">
        {error}
      </div>
    );
  }
  if (!standardData || !realData || !freezeData) {
    return (
      <div className="space-y-6">
        <div className="h-10 w-64 animate-pulse rounded bg-slate-200" />
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-20 animate-pulse rounded-xl border bg-slate-100" />
          ))}
        </div>
        <div className="h-[500px] animate-pulse rounded-xl border bg-slate-100" />
      </div>
    );
  }

  // Combine trajectories for the chart (standard + real policy + freeze)
  // Cap at 240 data points (20 years) to avoid rendering lag on long trajectories
  const maxLen = Math.min(240, Math.max(standardData.trajectory.length, realData.trajectory.length, freezeData.trajectory.length));
  const projection = Array.from({ length: maxLen }, (_, idx) => ({
    date: standardData.trajectory[idx]?.date || realData.trajectory[idx]?.date || freezeData.trajectory[idx]?.date || '',
    dateLabel: new Date(standardData.trajectory[idx]?.date || realData.trajectory[idx]?.date || freezeData.trajectory[idx]?.date || '').toLocaleDateString(undefined, { month: 'short', year: '2-digit' }),
    standardBacklog: standardData.trajectory[idx]?.backlog ?? 0,
    realBacklog: realData.trajectory[idx]?.backlog ?? 0,
    freezeBacklog: freezeData.trajectory[idx]?.backlog ?? 0
  }));

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-navy-900">Backlog Comparison</h2>
        <p className="text-slate-500">Comparing Standard INA Flow vs. 75-Country Freeze Impact.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">Standard Clearance</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-slate-400">
              {standardData.cleared === false
                ? 'Never Clears'
                : new Date(standardData.clearance_date).toLocaleDateString(undefined, { month: 'short', year: 'numeric' })}
            </div>
          </CardContent>
        </Card>
        <Card className="border-navy-200 bg-navy-50/30">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-navy-800">Real Policy Clearance</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-700">
              {realData.cleared === false
                ? 'Never Clears'
                : new Date(realData.clearance_date).toLocaleDateString(undefined, { month: 'short', year: 'numeric' })}
            </div>
          </CardContent>
        </Card>
        <Card className="border-crimson-200 bg-crimson-50/30">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-crimson-800">Restriction Clearance</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-crimson-600">
              {freezeData.cleared === false
                ? 'Never Clears'
                : new Date(freezeData.clearance_date).toLocaleDateString(undefined, { month: 'short', year: 'numeric' })}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-navy-700">Acceleration</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">
              {standardData.cleared === false
                ? 'Standard: Never Clears'
                : `${Math.round((standardData.months_to_clear ?? 0) - (freezeData.months_to_clear ?? 0))} Months Faster`}
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
                  <linearGradient id="colorReal" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#002868" stopOpacity={0.1}/>
                    <stop offset="95%" stopColor="#002868" stopOpacity={0}/>
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
                  formatter={(value) => [(value ?? 0).toLocaleString(), 'Backlog']}
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
                  dataKey="realBacklog" 
                  name="Real Policy"
                  stroke="#002868" 
                  strokeWidth={2}
                  strokeDasharray="5 3"
                  fillOpacity={1} 
                  fill="url(#colorReal)" 
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
