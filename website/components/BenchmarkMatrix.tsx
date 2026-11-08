"use client";

import { Check, X, Minus, HelpCircle, Trophy } from "lucide-react";

interface MatrixRow {
  feature: string;
  category: string;
  veloroute: string | boolean;
  litellm: string | boolean;
  portkey: string | boolean;
  rawApis: string | boolean;
  highlight?: boolean;
}

const COMPARISON: MatrixRow[] = [
  {
    feature: "Gateway Routing Overhead",
    category: "Performance",
    veloroute: "< 0.8ms (Microsecond)",
    litellm: "8 – 25ms",
    portkey: "15 – 45ms (Cloud RTT)",
    rawApis: "0ms (Direct)",
    highlight: true,
  },
  {
    feature: "Memory Footprint",
    category: "Performance",
    veloroute: "~34 MB RAM",
    litellm: "280+ MB RAM",
    portkey: "Hosted Cloud",
    rawApis: "0 MB",
    highlight: true,
  },
  {
    feature: "AST Python Context Skeletonizer",
    category: "Token Optimization",
    veloroute: true,
    litellm: false,
    portkey: false,
    rawApis: false,
    highlight: true,
  },
  {
    feature: "Caveman & Lossless ANSI Trimming",
    category: "Token Optimization",
    veloroute: true,
    litellm: false,
    portkey: false,
    rawApis: false,
  },
  {
    feature: "KV-Cache Prefix Affinity Routing",
    category: "Latency & Cost",
    veloroute: true,
    litellm: false,
    portkey: false,
    rawApis: false,
    highlight: true,
  },
  {
    feature: "Mid-Stream Automated Failover",
    category: "Resilience",
    veloroute: true,
    litellm: "Restart from chunk 0",
    portkey: false,
    rawApis: false,
  },
  {
    feature: "Parallel Speculative Hedging (/hedge)",
    category: "Resilience",
    veloroute: true,
    litellm: false,
    portkey: false,
    rawApis: false,
  },
  {
    feature: "Sentinel 3-State Circuit Breakers",
    category: "Resilience",
    veloroute: true,
    litellm: "Basic retry counter",
    portkey: "Partial (Cloud)",
    rawApis: false,
  },
  {
    feature: "Shannon Entropy Zero-Retention Shield",
    category: "Security",
    veloroute: true,
    litellm: "Regex only",
    portkey: "Stored on Portkey Cloud",
    rawApis: false,
    highlight: true,
  },
  {
    feature: "Universal MCP Bridge (stdio + SSE)",
    category: "Extensibility",
    veloroute: true,
    litellm: false,
    portkey: false,
    rawApis: false,
  },
  {
    feature: "Zero External Mandatory Databases",
    category: "Simplicity",
    veloroute: true,
    litellm: "Redis/Postgres required",
    portkey: "SaaS Database",
    rawApis: true,
  },
  {
    feature: "100% Open-Source & Self-Hostable",
    category: "Licensing",
    veloroute: "MIT License",
    litellm: "Enterprise features locked",
    portkey: "Proprietary Cloud Core",
    rawApis: "N/A",
  },
];

export default function BenchmarkMatrix() {
  const renderValue = (val: string | boolean, isVelo: boolean) => {
    if (typeof val === "boolean") {
      return val ? (
        <div className="flex items-center justify-center">
          <span
            className={`w-6 h-6 rounded-full flex items-center justify-center ${
              isVelo
                ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40"
                : "bg-slate-800 text-slate-400"
            }`}
          >
            <Check className="w-4 h-4 stroke-[2.5]" />
          </span>
        </div>
      ) : (
        <div className="flex items-center justify-center">
          <span className="w-6 h-6 rounded-full flex items-center justify-center bg-rose-500/10 text-rose-500/70 border border-rose-500/20">
            <X className="w-3.5 h-3.5 stroke-[2]" />
          </span>
        </div>
      );
    }
    return (
      <span
        className={`font-mono text-xs ${
          isVelo ? "text-emerald-400 font-bold" : "text-slate-300"
        }`}
      >
        {val}
      </span>
    );
  };

  return (
    <section id="benchmarks" className="py-24 relative border-t border-white/5 bg-[#080c14]/40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-amber-950/60 border border-amber-500/30 text-amber-400 text-xs font-mono mb-4">
            <Trophy className="w-3.5 h-3.5" />
            <span>Architecture Benchmark</span>
          </div>
          <h2 className="text-3xl sm:text-5xl font-extrabold text-white tracking-tight">
            How VeloRoute Compares.
          </h2>
          <p className="mt-4 text-slate-400 text-base sm:text-lg">
            Built from first principles for ultra-low latency, zero mandatory database dependencies,
            and deterministic token optimization.
          </p>
        </div>

        {/* Comparison Table */}
        <div className="overflow-x-auto rounded-2xl glass-panel border border-white/10 shadow-2xl">
          <table className="w-full text-left border-collapse min-w-[700px]">
            <thead>
              <tr className="border-b border-white/10 bg-slate-950/90 text-xs uppercase tracking-wider text-slate-400">
                <th className="py-4 px-6 font-semibold">Capability</th>
                <th className="py-4 px-6 font-semibold text-center bg-sky-950/40 border-x border-sky-500/30 text-sky-300">
                  ⚡ VeloRoute
                </th>
                <th className="py-4 px-6 font-semibold text-center">LiteLLM</th>
                <th className="py-4 px-6 font-semibold text-center">Portkey</th>
                <th className="py-4 px-6 font-semibold text-center">Raw Provider APIs</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 text-sm">
              {COMPARISON.map((row, idx) => (
                <tr
                  key={idx}
                  className={`hover:bg-slate-900/50 transition-colors ${
                    row.highlight ? "bg-white/[0.01]" : ""
                  }`}
                >
                  <td className="py-3.5 px-6 font-medium text-slate-200">
                    <div className="flex flex-col">
                      <span>{row.feature}</span>
                      <span className="text-[10px] text-slate-500 font-mono">{row.category}</span>
                    </div>
                  </td>
                  <td className="py-3.5 px-6 text-center bg-sky-950/20 border-x border-sky-500/20">
                    {renderValue(row.veloroute, true)}
                  </td>
                  <td className="py-3.5 px-6 text-center">{renderValue(row.litellm, false)}</td>
                  <td className="py-3.5 px-6 text-center">{renderValue(row.portkey, false)}</td>
                  <td className="py-3.5 px-6 text-center">{renderValue(row.rawApis, false)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
