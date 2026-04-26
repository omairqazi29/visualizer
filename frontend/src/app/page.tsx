"use client";

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getWaterfallData, getSupplyDemandData, WaterfallData, SupplyDemandData } from '@/lib/api';
import { Users, TrendingUp, Calendar, Zap } from 'lucide-react';

export default function Overview() {
  const [data, setData] = useState<WaterfallData | null>(null);
  const [sdData, setSdData] = useState<SupplyDemandData | null>(null);
  const [freezeWaterfall, setFreezeWaterfall] = useState<WaterfallData | null>(null);
  const [freezeSD, setFreezeSD] = useState<SupplyDemandData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      getWaterfallData(false), 
      getSupplyDemandData(false),
      getWaterfallData(true),
      getSupplyDemandData(true)
    ])
      .then(([w, sd, fw, fsd]) => {
        setData(w);
        setSdData(sd);
        setFreezeWaterfall(fw);
        setFreezeSD(fsd);
      })
      .catch((e) => setError(e?.message || 'Failed to load dashboard data'));
  }, []);

  if (error) return <div className="text-crimson-600">Error: {error}</div>;
  if (!data || !sdData || !freezeWaterfall || !freezeSD) return <div>Loading dashboard...</div>;

  const windfall = (freezeWaterfall.fb_savings_freeze || 0) + (freezeWaterfall.eb45_savings_freeze || 0);
  const acceleration = (sdData.months_to_clear || 0) - (freezeSD.months_to_clear || 0);

  return (
    <div className="space-y-8">
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-3xl font-bold tracking-tight text-navy-900">Dashboard Overview</h2>
          <p className="text-slate-500">Predicting the Impact of 2026/2027 U.S. Immigrant Visa Restrictions</p>
        </div>
        <div className="flex gap-2">
          <div className="px-3 py-1 bg-crimson-600 text-white text-xs font-bold rounded-full flex items-center gap-1 animate-pulse">
            <Zap className="w-3 h-3 fill-white" />
            Restriction Mode Active
          </div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card className="border-crimson-100 bg-crimson-50/20">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-bold text-crimson-800 uppercase tracking-wider">Trump Windfall</CardTitle>
            <Zap className="h-4 w-4 text-crimson-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">+{windfall?.toLocaleString()}</div>
            <p className="text-xs text-crimson-600 font-medium">Extra visas from bans & freezes</p>
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-slate-500 uppercase tracking-wider">India EB-1 Queue</CardTitle>
            <Users className="h-4 w-4 text-navy-800" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-navy-900">{sdData.total_queue?.toLocaleString()}</div>
            <p className="text-xs text-slate-400">Inventory + Pipeline</p>
          </CardContent>
        </Card>

        <Card className="border-emerald-100 bg-emerald-50/20">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-bold text-emerald-800 uppercase tracking-wider">Acceleration</CardTitle>
            <TrendingUp className="h-4 w-4 text-emerald-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-emerald-700">{acceleration} Months</div>
            <p className="text-xs text-emerald-600 font-medium">Faster clearance due to bans</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-slate-500 uppercase tracking-wider">Projected Date</CardTitle>
            <Calendar className="h-4 w-4 text-navy-800" />
          </CardHeader>
          <CardContent>
            <div className="text-xl font-bold text-navy-900">
              {freezeSD.clearance_date ? new Date(freezeSD.clearance_date).toLocaleDateString(undefined, { month: 'short', year: 'numeric' }) : 'N/A'}
            </div>
            <p className="text-xs text-slate-400">Restriction-adjusted</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
        <Card className="col-span-4">
          <CardHeader>
            <CardTitle className="text-navy-900">The Restriction Delta Analysis</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-slate-600">
            <p>
              Under the current administrative stance, travel bans and 75-country freezes effectively redirect thousands of unused visas
              from restricted regions back into the general employment-based pool.
            </p>
            <div className="grid grid-cols-2 gap-4">
              <div className="p-4 border rounded-lg bg-slate-50">
                <h4 className="font-semibold text-navy-900 mb-1 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-crimson-600" />
                  Bypassing 7% Caps
                </h4>
                <p className="text-sm">Unused visas spill over to backlogged countries by priority date, ignoring per-country limits.</p>
              </div>
              <div className="p-4 border rounded-lg bg-slate-50">
                <h4 className="font-semibold text-navy-900 mb-1 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-navy-900" />
                  EB-4/5 Spill-Up
                </h4>
                <p className="text-sm">Restrictions on investor and special categories funnel 100% of unused capacity to EB-1.</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="col-span-3">
          <CardHeader>
            <CardTitle>Data Sources</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3 text-sm text-slate-600">
              <li className="flex items-center gap-2">
                <Badge variant="outline" className="text-[10px] h-4">DOS</Badge>
                Monthly Issuances: FY2025 sequence
              </li>
              <li className="flex items-center gap-2">
                <Badge variant="outline" className="text-[10px] h-4">USCIS</Badge>
                EB Inventory: January 2026
              </li>
              <li className="flex items-center gap-2">
                <Badge variant="outline" className="text-[10px] h-4">USCIS</Badge>
                Performance Data: FY2025 Q4
              </li>
            </ul>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
