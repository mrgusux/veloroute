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
            className={`w-5 h-5 rounded-none flex items-center justify-center ${
              isVelo
                ? "bg-[#0055FF] text-[#FBFBFF]"
                : "bg-[#18181C] text-[#A7A9B8]"
            }`}
          >
            <Check className="w-3.5 h-3.5 stroke-[2.5]" />
          </span>
        </div>
      ) : (
        <div className="flex items-center justify-center">
          <span className="w-5 h-5 rounded-none flex items-center justify-center bg-[#18181C] text-[#5B5D6B]">
            <X className="w-3 h-3 stroke-[2]" />
          </span>
        </div>
      );
    }
    return (
      <span
        className={`font-mono text-xs ${
          isVelo ? "text-[#0055FF] font-bold" : "text-[#A7A9B8]"
        }`}
      >
        {val}
      </span>
    );
  };

  return (
    <section id="benchmarks" className="py-24 relative border-t border-[#18181C] bg-[#000000]">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-8 lg:px-[120px]">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-none bg-[#111114] border border-[#18181C] text-[#0055FF] text-[11px] font-mono uppercase tracking-widest mb-4">
            <Trophy className="w-3.5 h-3.5 text-[#0055FF]" />
            <span>ARCHITECTURE BENCHMARK</span>
          </div>
          <h2 className="text-3xl sm:text-5xl font-bold text-[#FBFBFF] tracking-tight">
            How VeloRoute Compares.
          </h2>
          <p className="mt-4 text-[#A7A9B8] text-base sm:text-lg">
            Built from first principles for ultra-low latency, zero mandatory database dependencies,
            and deterministic token optimization.
          </p>
        </div>

        {/* Comparison Table */}
        <div className="overflow-x-auto rounded-none bg-[#0B0B0D] border border-[#18181C] shadow-none">
          <table className="w-full text-left border-collapse min-w-[700px]">
            <thead>
              <tr className="border-b border-[#18181C] bg-[#000000] text-xs uppercase tracking-wider text-[#A7A9B8]">
                <th className="py-4 px-6 font-semibold">Capability</th>
                <th className="py-4 px-6 font-semibold text-center bg-[#111114] border-x border-[#18181C] text-[#0055FF]">
                  ⚡ VeloRoute
                </th>
                <th className="py-4 px-6 font-semibold text-center">LiteLLM</th>
                <th className="py-4 px-6 font-semibold text-center">Portkey</th>
                <th className="py-4 px-6 font-semibold text-center">Raw Provider APIs</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#18181C] text-sm">
              {COMPARISON.map((row, idx) => (
                <tr
                  key={idx}
                  className={`hover:bg-[#111114] transition-colors ${
                    row.highlight ? "bg-white/[0.02]" : ""
                  }`}
                >
                  <td className="py-3.5 px-6 font-medium text-[#DFE0EA]">
                    <div className="flex flex-col">
                      <span>{row.feature}</span>
                      <span className="text-[10px] text-[#5B5D6B] font-mono uppercase tracking-wider">{row.category}</span>
                    </div>
                  </td>
                  <td className="py-3.5 px-6 text-center bg-[#111114]/80 border-x border-[#18181C]">
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
