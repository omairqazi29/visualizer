"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getMethodology, MethodologyData } from "@/lib/api";
import { ExternalLink, ShieldCheck, ShieldAlert, Database, Scale, BookOpen } from "lucide-react";

export default function Methodology() {
  const [data, setData] = useState<MethodologyData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMethodology()
      .then(setData)
      .catch((e) => setError(e?.message || "Failed to load methodology data"));
  }, []);

  if (error) {
    return (
      <div className="rounded-lg border border-crimson-200 bg-crimson-50 p-4 text-crimson-700">
        {error}
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-6">
        <div className="h-10 w-64 animate-pulse rounded bg-slate-200" />
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-40 animate-pulse rounded-xl border bg-slate-100" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-4xl">
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-navy-900">
          Methodology & Data Sources
        </h2>
        <p className="text-slate-500 mt-1">
          Transparency into the data, assumptions, and legal context behind projections.
          Last verified: <span className="font-semibold text-navy-900">{data.last_verified}</span>
        </p>
      </div>

      {/* Model Parameters */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-navy-900">
            <BookOpen className="w-5 h-5" />
            Model Parameters (INA 201/203)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="p-3 rounded-lg bg-slate-50 border">
              <div className="text-xs text-slate-500 uppercase tracking-wider">EB Base Limit</div>
              <div className="text-xl font-bold text-navy-900">{data.eb_base_limit.toLocaleString()}</div>
              <div className="text-xs text-slate-400">INA 203(b)</div>
            </div>
            <div className="p-3 rounded-lg bg-slate-50 border">
              <div className="text-xs text-slate-500 uppercase tracking-wider">FB Floor</div>
              <div className="text-xl font-bold text-navy-900">{data.fb_statutory_limit.toLocaleString()}</div>
              <div className="text-xs text-slate-400">INA 201(c)</div>
            </div>
            <div className="p-3 rounded-lg bg-slate-50 border">
              <div className="text-xs text-slate-500 uppercase tracking-wider">India EB-1 Baseline</div>
              <div className="text-xl font-bold text-navy-900">{data.india_eb1_baseline.toLocaleString()}</div>
              <div className="text-xs text-slate-400">FY2024 actuals</div>
            </div>
            <div className="p-3 rounded-lg bg-slate-50 border">
              <div className="text-xs text-slate-500 uppercase tracking-wider">Dependent Mult.</div>
              <div className="text-xl font-bold text-navy-900">{data.dependent_multiplier}x</div>
              <div className="text-xs text-slate-400">I-140 to heads</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Data Sources */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-navy-900">
            <Database className="w-5 h-5" />
            Data Sources
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {data.data_sources.map((src, i) => (
              <div key={i} className="flex items-start gap-4 p-4 rounded-lg border bg-slate-50/50">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <h4 className="font-semibold text-navy-900">{src.name}</h4>
                    <a
                      href={src.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-slate-400 hover:text-navy-900 transition-colors"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  </div>
                  <p className="text-sm text-slate-600">{src.description}</p>
                  <div className="flex gap-3 mt-2">
                    <Badge variant="outline" className="text-[10px]">
                      Coverage: {src.coverage}
                    </Badge>
                    <Badge variant="outline" className="text-[10px]">
                      Updates: {src.update_frequency}
                    </Badge>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Legal Status */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-navy-900">
            <Scale className="w-5 h-5" />
            Legal & Policy Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {data.legal_status.map((item, i) => {
              const isActive = item.status.toLowerCase().startsWith("in effect");
              return (
                <div
                  key={i}
                  className={`p-4 rounded-lg border ${
                    isActive ? "border-crimson-200 bg-crimson-50/30" : "border-emerald-200 bg-emerald-50/30"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    {isActive ? (
                      <ShieldAlert className="w-4 h-4 text-crimson-600" />
                    ) : (
                      <ShieldCheck className="w-4 h-4 text-emerald-600" />
                    )}
                    <h4 className="font-semibold text-navy-900">{item.policy}</h4>
                    <Badge
                      className={`text-[10px] ${
                        isActive
                          ? "bg-crimson-100 text-crimson-700 border-crimson-200"
                          : "bg-emerald-100 text-emerald-700 border-emerald-200"
                      }`}
                      variant="outline"
                    >
                      {item.status}
                    </Badge>
                  </div>
                  <p className="text-sm text-slate-600 mb-2">{item.description}</p>
                  <p className="text-xs text-slate-500">
                    <span className="font-medium">Model impact:</span> {item.model_impact}
                  </p>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Restricted Countries */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-navy-900">
            <ShieldAlert className="w-5 h-5" />
            Restricted Countries ({data.restricted_countries_count})
            <Badge variant="outline" className="text-[10px] ml-2">
              Proclamations + DOS IV Pause
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-slate-500 mb-4">
            Union of 39-country Proclamation entry ban + 75-country DOS public charge IV pause.
            India and China are explicitly excluded. Consular IV savings from these countries
            are computed from actual DOS issuance data and redistributed via INA 202(a)(5) surplus rules.
          </p>
          <div className="flex flex-wrap gap-2">
            {data.restricted_countries.map((country) => (
              <Badge
                key={country}
                variant="outline"
                className="text-xs bg-slate-50"
              >
                {country}
              </Badge>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Verification Process */}
      <Card>
        <CardHeader>
          <CardTitle className="text-navy-900">Verification Process</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-slate-600 space-y-3">
          <p>
            All numbers are derived from official U.S. government sources (DOS, USCIS).
            The verification process is documented in{" "}
            <code className="text-xs bg-slate-100 px-1.5 py-0.5 rounded">docs/POLICY_VERIFICATION.md</code>.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="p-3 rounded border bg-slate-50">
              <h5 className="font-medium text-navy-900 mb-1">Data Updates</h5>
              <p className="text-xs">
                Drop new DOS/USCIS Excel files into <code className="bg-slate-100 px-1 rounded">data/</code> — auto-discovered by filename date. No code changes needed.
              </p>
            </div>
            <div className="p-3 rounded border bg-slate-50">
              <h5 className="font-medium text-navy-900 mb-1">Policy Updates</h5>
              <p className="text-xs">
                Country list changes: edit <code className="bg-slate-100 px-1 rounded">src/constants.py</code>.
                Court rulings: verify whether they affect consular IVs (DOS data) or only USCIS domestic processing.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}