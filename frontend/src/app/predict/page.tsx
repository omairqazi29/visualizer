"use client";

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { predictPD } from '@/lib/api';
import { Calculator, Calendar, CheckCircle2, AlertCircle } from 'lucide-react';

export default function PredictorPage() {
  const [pd, setPd] = useState('2025-01-16');
  const [burnRate, setBurnRate] = useState(2000);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const handlePredict = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const data = await predictPD(pd, burnRate);
      setResult(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const getConfidenceColor = (score: number) => {
    if (score > 0.8) return 'text-emerald-600 bg-emerald-50';
    if (score > 0.5) return 'text-amber-600 bg-amber-50';
    return 'text-crimson-600 bg-crimson-50';
  };

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-navy-900">Priority Date Predictor</h2>
        <p className="text-slate-500">Estimate your approval confidence for Fiscal Year 2027.</p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Enter Your Details</CardTitle>
            <CardDescription>We use the current inventory and pipeline estimates to calculate your place in line.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handlePredict} className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Priority Date</label>
                <Input 
                  type="date" 
                  value={pd} 
                  onChange={(e) => setPd(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Projected Monthly Burn Rate</label>
                <Input 
                  type="number" 
                  value={burnRate} 
                  onChange={(e) => setBurnRate(parseInt(e.target.value))}
                  required
                />
              </div>
              <Button type="submit" className="w-full bg-navy-900 hover:bg-navy-800" disabled={loading}>
                {loading ? 'Calculating...' : 'Calculate Prediction'}
              </Button>
            </form>
          </CardContent>
        </Card>

        {result && (
          <Card className="border-2 border-navy-900/10">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                Prediction Results
                <Badge variant="outline" className={getConfidenceColor(result.confidence_score)}>
                  {(result.confidence_score * 100).toFixed(0)}% Confidence
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-navy-50 rounded-full text-navy-900">
                  <Calculator className="w-6 h-6" />
                </div>
                <div>
                  <p className="text-sm text-slate-500 font-medium">Estimated Backlog Ahead</p>
                  <p className="text-2xl font-bold text-navy-900">{result.backlog_ahead.toLocaleString()}</p>
                </div>
              </div>

              <div className="flex items-center gap-4">
                <div className="p-3 bg-crimson-50 rounded-full text-crimson-600">
                  <Calendar className="w-6 h-6" />
                </div>
                <div>
                  <p className="text-sm text-slate-500 font-medium">Projected GC Availability</p>
                  <p className="text-2xl font-bold text-navy-900">
                    {new Date(result.projected_clearance_date).toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}
                  </p>
                </div>
              </div>

              <div className="p-4 rounded-lg bg-slate-50 border space-y-2">
                <p className="text-xs font-bold uppercase tracking-wider text-slate-400">Analysis</p>
                {result.confidence_score > 0.7 ? (
                  <p className="text-sm text-slate-600 flex items-start gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />
                    Your priority date is well-positioned for FY 2027 based on current spillover projections and historical burn rates.
                  </p>
                ) : (
                  <p className="text-sm text-slate-600 flex items-start gap-2">
                    <AlertCircle className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />
                    Given the current backlog and burn rate, your approval may fall into late FY 2027 or early FY 2028.
                  </p>
                )}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
