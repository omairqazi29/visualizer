"use client";

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { predictPD, PredictData } from '@/lib/api';
import { Calendar, ArrowRight } from 'lucide-react';

export default function PredictorPage() {
  const [pd, setPd] = useState('2025-01-16');
  const [standardResult, setStandardResult] = useState<PredictData | null>(null);
  const [freezeResult, setFreezeResult] = useState<PredictData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runPrediction = async (dateStr: string) => {
    setLoading(true);
    setError(null);
    try {
      const [std, frz] = await Promise.all([
        predictPD(dateStr, false, false),  // Baseline (no restrictions)
        predictPD(dateStr, false, true)    // Current policy (91-country real restrictions)
      ]);
      setStandardResult(std);
      setFreezeResult(frz);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      const message = e?.response?.data?.detail || 'Prediction request failed';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const handlePredict = (e: React.FormEvent) => {
    e.preventDefault();
    runPrediction(pd);
  };

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-navy-900">Personal PD Predictor</h2>
        <p className="text-slate-500">Predicts when the <span className="font-semibold">Final Action Date (FAD)</span> reaches your priority date — i.e., when your visa number becomes available for approval. Compare baseline vs. current 91-country policy.</p>
      </div>

      <Card className="max-w-md">
        <CardHeader>
          <CardTitle>Priority Date</CardTitle>
          <CardDescription>Enter your I-140 Priority Date to see the impact.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handlePredict} className="flex gap-4">
            <Input 
              type="date" 
              value={pd} 
              onChange={(e) => setPd(e.target.value)}
              required
              className="flex-1"
            />
            <Button type="submit" className="bg-navy-900 hover:bg-navy-800" disabled={loading}>
              {loading ? '...' : 'Compare Results'}
            </Button>
          </form>

          <div className="mt-3 flex flex-wrap gap-2">
            {[
              { label: 'Jan 2024', value: '2024-01-15' },
              { label: 'Jul 2024', value: '2024-07-01' },
              { label: 'Jan 2025', value: '2025-01-01' },
              { label: 'Current (Apr 2023)', value: '2023-04-01' },
            ].map((p) => (
              <button
                key={p.value}
                type="button"
                onClick={() => {
                  setPd(p.value);
                  runPrediction(p.value);
                }}
                className="rounded-md border px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-50"
              >
                {p.label}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {error && (
        <div className="rounded-lg border border-crimson-200 bg-crimson-50 p-4 text-crimson-700 max-w-md">
          {error}
        </div>
      )}

      {standardResult && freezeResult && (
        <div className="space-y-4">
          <div className="grid gap-6 md:grid-cols-2">
            {/* Standard Result */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  Baseline
                  <Badge variant="outline">No Restrictions</Badge>
                </CardTitle>
                <CardDescription>Standard INA flow — no administrative restrictions applied.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="flex items-center gap-4">
                  <div className="p-3 bg-slate-100 rounded-full text-slate-600">
                    <Calendar className="w-6 h-6" />
                  </div>
                  <div>
                    <p className="text-sm text-slate-500 font-medium">FAD Reaches Your PD</p>
                    <p className="text-2xl font-bold text-slate-700">
                      {new Date(standardResult.projected_clearance_date).toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}
                    </p>
                  </div>
                </div>
                
                <div className="p-4 rounded-lg bg-slate-50 border space-y-2">
                  <p className="text-xs font-bold uppercase tracking-wider text-slate-400">Confidence</p>
                  <div className="flex items-center gap-2">
                    <div className="h-2 flex-1 bg-slate-200 rounded-full overflow-hidden">
                      <div 
                        className="h-full bg-slate-400" 
                        style={{ width: `${standardResult.confidence_score * 100}%` }}
                      />
                    </div>
                    <span className="text-sm font-bold text-slate-600">{(standardResult.confidence_score * 100).toFixed(0)}%</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Restriction Result */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  Current Policy
                  <Badge className="bg-crimson-600">91 Countries</Badge>
                </CardTitle>
                <CardDescription>91-country restrictions (Proclamation ban + DOS IV pause) — savings from DOS data.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="flex items-center gap-4">
                  <div className="p-3 bg-crimson-50 rounded-full text-crimson-600">
                    <Calendar className="w-6 h-6" />
                  </div>
                  <div>
                    <p className="text-sm text-slate-500 font-medium">FAD Reaches Your PD</p>
                    <p className="text-2xl font-bold text-navy-900">
                      {new Date(freezeResult.projected_clearance_date).toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}
                    </p>
                  </div>
                </div>

                <div className="p-4 rounded-lg bg-crimson-50/50 border border-crimson-100 space-y-2">
                  <p className="text-xs font-bold uppercase tracking-wider text-crimson-600">Confidence</p>
                  <div className="flex items-center gap-2">
                    <div className="h-2 flex-1 bg-crimson-200 rounded-full overflow-hidden">
                      <div 
                        className="h-full bg-crimson-600" 
                        style={{ width: `${freezeResult.confidence_score * 100}%` }}
                      />
                    </div>
                    <span className="text-sm font-bold text-crimson-700">{(freezeResult.confidence_score * 100).toFixed(0)}%</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Delta Summary */}
          <Card className="border-emerald-200 bg-emerald-50/40">
            <CardContent className="pt-6">
              <div className="flex flex-col items-center justify-center gap-1 text-center">
                <div className="flex items-center gap-2 text-emerald-700">
                  <ArrowRight className="w-5 h-5" />
                  <span className="text-2xl font-bold">
                    {Math.round((standardResult.months_to_clear - freezeResult.months_to_clear))} Months Earlier
                  </span>
                </div>
                <p className="text-sm text-emerald-600">Due to increased EB-1 supply from restriction-driven spillovers</p>
              </div>
            </CardContent>
          </Card>

          <p className="text-xs text-slate-400 italic">
            <span className="font-semibold text-slate-500">FAD vs DOF:</span>{' '}
            This model predicts the <span className="font-medium">Final Action Date (FAD)</span> — the date
            your visa number becomes available and your green card can be approved. The{' '}
            <span className="font-medium">Date of Filing (DOF)</span>, which controls when you can
            submit your I-485, typically advances faster and is not modeled here. Once your FAD is current,
            you are eligible for final adjudication.
          </p>
        </div>
      )}
    </div>
  );
}
