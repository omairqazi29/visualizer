"use client";

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Slider } from "@/components/ui/slider";
import { getSupplyDemandData } from '@/lib/api';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export default function SupplyDemandPage() {
  const [data, setData] = useState<any>(null);
  const [burnRate, setBurnRate] = useState<number>(2000);
  const [projection, setProjection] = useState<any[]>([]);

  useEffect(() => {
    getSupplyDemandData().then(d => {
      setData(d);
      setBurnRate(d.dynamic_burn_rate);
    });
  }, []);

  useEffect(() => {
    if (data) {
      const proj = [];
      let current = data.total_queue;
      for (let i = 0; i <= 36; i++) {
        proj.push({
          month: i,
          queue: Math.max(0, current)
        });
        current -= burnRate;
      }
      setProjection(proj);
    }
  }, [data, burnRate]);

  if (!data) return <div>Loading...</div>;

  const clearanceDate = new Date();
  clearanceDate.setMonth(clearanceDate.getMonth() + Math.ceil(data.total_queue / burnRate));

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-navy-900">Supply/Demand Curve</h2>
        <p className="text-slate-500">Visualizing the clearance of the India EB-1 backlog.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">I-485 Inventory</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">{data.inventory.total.toLocaleString()}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">I-140 Pipeline (est.)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">{data.pipeline_total.toLocaleString()}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">Total Queue</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-crimson-600">{data.total_queue.toLocaleString()}</div>
          </CardContent>
        </Card>
      </div>

      <Card className="p-6">
        <CardHeader>
          <CardTitle>Queue Clearance Projection</CardTitle>
          <CardDescription>Estimated clearance based on monthly visa burn rate.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="mb-8 space-y-4">
            <div className="flex justify-between items-center">
              <label className="text-sm font-medium">Monthly Burn Rate: <span className="text-navy-900 font-bold">{burnRate.toLocaleString()}</span></label>
              <span className="text-xs text-slate-400">Default: {data.dynamic_burn_rate.toLocaleString()}</span>
            </div>
            <Slider 
              value={[burnRate]} 
              min={500} 
              max={5000} 
              step={100} 
              onValueChange={(val) => setBurnRate(val[0])}
            />
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
                <XAxis dataKey="month" label={{ value: 'Months from Jan 2026', position: 'insideBottom', offset: -5 }} />
                <YAxis />
                <Tooltip />
                <Area 
                  type="monotone" 
                  dataKey="queue" 
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
              <p className="text-2xl font-bold">{clearanceDate.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}</p>
            </div>
            <div className="text-right">
              <p className="text-navy-200 text-xs uppercase tracking-wider font-bold">Total Months</p>
              <p className="text-2xl font-bold">{Math.ceil(data.total_queue / burnRate)}</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
