"use client";

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { getSupplyDemandData } from '@/lib/api';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export default function SupplyDemandPage() {
  const [data, setData] = useState<any>(null);
  const [applyFreeze, setApplyFreeze] = useState<boolean>(false);

  useEffect(() => {
    getSupplyDemandData(applyFreeze).then(d => {
      setData(d);
    });
  }, [applyFreeze]);

  if (!data) return <div>Loading...</div>;

  const projection = data.trajectory.map((t: any, idx: number) => ({
    ...t,
    month: idx,
    dateLabel: new Date(t.date).toLocaleDateString(undefined, { month: 'short', year: '2-digit' })
  }));

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-navy-900">Supply/Demand Curve</h2>
        <p className="text-slate-500">Visualizing the clearance of the India EB-1 backlog.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {/* ... stats cards ... */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">I-485 Inventory</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">{data.inventory?.total?.toLocaleString()}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">I-140 Pipeline (est.)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">{data.pipeline_total?.toLocaleString()}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">Total Queue</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-crimson-600">{data.total_queue?.toLocaleString()}</div>
          </CardContent>
        </Card>
      </div>

      <Card className="p-6">
        <CardHeader>
          <CardTitle>Queue Clearance Projection</CardTitle>
          <CardDescription>Estimated clearance based on non-linear historical seasonality.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="mb-8 p-4 bg-slate-50 rounded-lg border border-slate-200 flex items-center justify-between">
            <div className="space-y-1">
              <h4 className="text-sm font-bold text-navy-900">Simulation: 75-Country Freeze</h4>
              <p className="text-xs text-slate-500">Reallocate unused visas from restricted countries to the surplus pool.</p>
            </div>
            <Button 
              variant={applyFreeze ? "default" : "outline"}
              onClick={() => setApplyFreeze(!applyFreeze)}
              className={applyFreeze ? "bg-crimson-600 hover:bg-crimson-700" : ""}
            >
              {applyFreeze ? "Disable Simulation" : "Enable Simulation"}
            </Button>
          </div>

          <div className="h-[400px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={projection}>
                <defs>
                  <linearGradient id="colorQueue" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#002868" stopOpacity={0.1}/>
                    <stop offset="95%" stopColor="#002868" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="dateLabel" />
                <YAxis />
                <Tooltip labelFormatter={(val, items) => items[0]?.payload?.date} />
                <Area 
                  type="monotone" 
                  dataKey="backlog" 
                  name="Backlog"
                  stroke="#002868" 
                  strokeWidth={2}
                  fillOpacity={1} 
                  fill="url(#colorQueue)" 
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          
          <div className="mt-6 p-4 bg-navy-900 rounded-lg text-white flex justify-between items-center">
            <div>
              <p className="text-navy-200 text-xs uppercase tracking-wider font-bold">Projected Clearance</p>
              <p className="text-2xl font-bold">{new Date(data.clearance_date).toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}</p>
            </div>
            <div className="text-right">
              <p className="text-navy-200 text-xs uppercase tracking-wider font-bold">Total Supply (Annual)</p>
              <p className="text-2xl font-bold">{data.annual_eb1_supply?.toLocaleString()}</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
