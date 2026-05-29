"use client";

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getDataSources, DataSourcesData } from '@/lib/api';
import { useWaterfallData } from '@/lib/hooks/useWaterfallData';
import { useSupplyDemandData } from '@/lib/hooks/useSupplyDemandData';
import { Users, TrendingUp, Calendar, Zap, Database } from 'lucide-react';

export default function Overview() {
  // Dashboard shows standard vs. freeze (hypothetical) delta only.
  // Real-policy scenario is intentionally omitted here — available on the
  // supply-demand detail page where all three are compared side-by-side.
  const { data, error: waterfallError } = useWaterfallData('standard');
  const { data: freezeWaterfall, error: freezeWaterfallError } = useWaterfallData('freeze');
  const { standardData: sdData, freezeData: freezeSD, error: sdError } = useSupplyDemandData();
  const [dataSources, setDataSources] = useState<DataSourcesData | null>(null);

  // Fetch data sources independently — failure should not break the dashboard
  useEffect(() => {
    getDataSources()
      .then(setDataSources)
      .catch(() => {}); // dataSources stays null; skeleton renders gracefully
  }, []);

  const error = waterfallError || freezeWaterfallError || sdError;

  if (error) {
    return (
      <div className="rounded-lg border border-crimson-200 bg-crimson-50 p-4 text-crimson-700">
        {error}
      </div>
    );
  }
  if (!data || !sdData || !freezeWaterfall || !freezeSD) {
    return (
      <div className="space-y-8">
        <div className="h-10 w-64 animate-pulse rounded bg-slate-200" />
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-28 animate-pulse rounded-xl border bg-slate-100" />
          ))}
        </div>
      </div>
    );
  }

  const windfall = (freezeWaterfall.fb_savings_freeze ?? 0) + (freezeWaterfall.eb45_savings_freeze ?? 0);
  const acceleration = (sdData.months_to_clear ?? 0) - (freezeSD.months_to_clear ?? 0);

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
            <CardTitle className="text-sm font-bold text-crimson-800 uppercase tracking-wider">Restriction Windfall</CardTitle>
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
            <div className="text-2xl font-bold text-emerald-700">
              {sdData.cleared === false ? 'N/A' : `${acceleration} Months`}
            </div>
            <p className="text-xs text-emerald-600 font-medium">
              {sdData.cleared === false ? 'Standard scenario never clears' : 'Faster clearance due to bans'}
            </p>
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
              <strong>Hypothetical Scenario:</strong> Models potential demand reductions (per INA 201/203 spillover). As of May 2026 Visa Bulletin, India EB-1 Final Action is 01APR23 (no enacted broad 75-country freeze). See research notes in docs/.
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
            <CardTitle className="flex items-center gap-2">
              <Database className="h-4 w-4 text-navy-800" />
              Data Sources
            </CardTitle>
          </CardHeader>
          <CardContent>
            {dataSources ? (
              <ul className="space-y-3 text-sm text-slate-600">
                <li className="flex items-center gap-2">
                  <Badge variant="outline" className="text-[10px] h-4">DOS</Badge>
                  Monthly Issuances: {dataSources.dos_files.length} files
                  {dataSources.dos_files.length > 0 && (
                    <span className="text-xs text-slate-400">
                      ({dataSources.dos_files[0]?.parsed_date} &ndash; {dataSources.dos_files[dataSources.dos_files.length - 1]?.parsed_date})
                    </span>
                  )}
                </li>
                <li className="flex items-center gap-2">
                  <Badge variant="outline" className="text-[10px] h-4">USCIS</Badge>
                  Inventory: {dataSources.inventory_file.filename.replace('.xlsx', '').replace(/_/g, ' ')}{!dataSources.inventory_file.exists && ' (not found)'}
                </li>
                <li className="flex items-center gap-2">
                  <Badge variant="outline" className="text-[10px] h-4">USCIS</Badge>
                  Pipeline: {dataSources.pipeline_file.parsed_date || dataSources.pipeline_file.filename.replace('.xlsx', '').replace(/_/g, ' ')}{!dataSources.pipeline_file.exists && ' (not found)'}
                </li>
              </ul>
            ) : (
              <div className="space-y-2">
                {Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="h-5 animate-pulse rounded bg-slate-100" />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
