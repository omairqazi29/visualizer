"use client";

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getWaterfallData, getSupplyDemandData } from '@/lib/api';
import { Users, BarChart, TrendingUp, Calendar } from 'lucide-react';

export default function Overview() {
  const [data, setData] = useState<any>(null);
  const [sdData, setSdData] = useState<any>(null);

  useEffect(() => {
    Promise.all([getWaterfallData(), getSupplyDemandData()])
      .then(([w, sd]) => {
        setData(w);
        setSdData(sd);
      });
  }, []);

  if (!data || !sdData) return <div>Loading dashboard...</div>;

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-navy-900">Dashboard Overview</h2>
        <p className="text-slate-500">Predicting the Impact of 2026/2027 U.S. Immigrant Visa Restrictions</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">Total EB-1 Supply</CardTitle>
            <BarChart className="h-4 w-4 text-crimson-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">{data.eb1_supply?.toLocaleString()}</div>
            <p className="text-xs text-slate-400">Projected for FY 2026/27</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">India EB-1 Queue</CardTitle>
            <Users className="h-4 w-4 text-navy-800" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">{sdData.total_queue?.toLocaleString()}</div>
            <p className="text-xs text-slate-400">Inventory + Pipeline</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">Projected Clearance</CardTitle>
            <TrendingUp className="h-4 w-4 text-emerald-600" />
          </CardHeader>
          <CardContent>
            <div className="text-xl font-bold text-navy-900">
              {sdData.clearance_date ? new Date(sdData.clearance_date).toLocaleDateString(undefined, { month: 'short', year: 'numeric' }) : 'N/A'}
            </div>
            <p className="text-xs text-slate-400">Non-linear projection</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">Spillover (FB)</CardTitle>
            <Calendar className="h-4 w-4 text-amber-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">{data.fb_spillover?.toLocaleString()}</div>
            <p className="text-xs text-slate-400">Redistributed from FB limits</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
        <Card className="col-span-4">
          <CardHeader>
            <CardTitle>Welcome to The Spillover Engine</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-slate-600">
            <p>
              This production-grade visualization and prediction platform is 
              designed to analyze the India EB-1 backlog under the latest Department of State (DOS) and USCIS data.
            </p>
            <div className="grid grid-cols-2 gap-4">
              <div className="p-4 border rounded-lg bg-slate-50">
                <h4 className="font-semibold text-navy-900 mb-1">INA-Logic Spillover</h4>
                <p className="text-sm">Flow from FB statutory limits through the '75-Country Freeze' to find the final EB-1 supply.</p>
              </div>
              <div className="p-4 border rounded-lg bg-slate-50">
                <h4 className="font-semibold text-navy-900 mb-1">Queue Tracking</h4>
                <p className="text-sm">Combines pending I-485 adjustment of status applications with approved I-140 pipeline.</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="col-span-3">
          <CardHeader>
            <CardTitle>Data Sources</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm text-slate-600">
              <li className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-navy-900" />
                DOS Monthly Issuances: FY2025 sequence
              </li>
              <li className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-navy-900" />
                USCIS EB Inventory: January 2026
              </li>
              <li className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-navy-900" />
                USCIS Performance Data: FY2025 Q4
              </li>
            </ul>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
