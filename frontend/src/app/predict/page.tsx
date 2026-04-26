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
  const [, setError] = useState<string | null>(null);  // error captured for future UI display

  const handlePredict = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const [std, frz] = await Promise.all([
        predictPD(pd, false),
        predictPD(pd, true)
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

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-navy-900">Personal PD Predictor</h2>
        <p className="text-slate-500">Estimate how travel bans and restrictions accelerate your specific Priority Date.</p>
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
        </CardContent>
      </Card>

      {standardResult && freezeResult && (
        <div className="grid gap-6 md:grid-cols-2">
          {/* Standard Result */}
          <Card className="opacity-80">
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                Standard INA Flow
                <Badge variant="outline">Normal Flow</Badge>
              </CardTitle>
              <CardDescription>Based on historical 9k/year supply baseline.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-slate-100 rounded-full text-slate-600">
                  <Calendar className="w-6 h-6" />
                </div>
                <div>
                  <p className="text-sm text-slate-500 font-medium">Projected Date</p>
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

          {/* Freeze Result */}
          <Card className="border-2 border-crimson-600 shadow-lg shadow-crimson-600/5">
            <CardHeader>
              <CardTitle className="flex items-center justify-between text-crimson-700">
                Restriction Mode
                <Badge className="bg-crimson-600">Trump Effect</Badge>
              </CardTitle>
              <CardDescription>Includes windfalls from travel bans and country freezes.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-crimson-50 rounded-full text-crimson-600">
                  <Calendar className="w-6 h-6" />
                </div>
                <div>
                  <p className="text-sm text-slate-500 font-medium">Accelerated Date</p>
                  <p className="text-2xl font-bold text-navy-900">
                    {new Date(freezeResult.projected_clearance_date).toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}
                  </p>
                </div>
              </div>

              <div className="p-4 rounded-lg bg-crimson-50/50 border border-crimson-100 space-y-2">
                <p className="text-xs font-bold uppercase tracking-wider text-crimson-600">Impact Analysis</p>
                <div className="flex items-center gap-2 text-navy-900 font-bold">
                  <ArrowRight className="w-4 h-4 text-crimson-600" />
                  {Math.round((standardResult.months_to_clear - freezeResult.months_to_clear))} Months Earlier
                </div>
                <p className="text-xs text-slate-500">
                  Higher supply confidence due to redistribution of unused visas.
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
