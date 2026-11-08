"use client";

import { useState } from "react";
import {
  Layers,
  Cpu,
  ShieldAlert,
  Zap,
  Lock,
  GitBranch,
  Network,
  Activity,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
} from "lucide-react";

interface StrategyItem {
  id: string;
  name: string;
  badge: string;
  badgeColor: string;
  icon: any;
  headline: string;
  description: string;
  bulletPoints: string[];
  visualType: "kv" | "sentinel" | "hedging" | "quality" | "privacy" | "mcp";
}

const STRATEGIES: StrategyItem[] = [
  {
    id: "kv_affinity",
    name: "KV-Cache Affinity",
    badge: "Hardware Cache Hits",
    badgeColor: "text-sky-400 border-sky-800 bg-sky-950/60",
    icon: Layers,
    headline: "Pin Prefixes to Warm GPU Instances to Slash 80% Input Latency & Cost",
    description:
      "VeloRoute hashes incoming system prompts, large context windows, and codebase skeletons with SHA-256. Requests sharing the identical prefix are sticky-routed to the exact same provider cluster or vLLM node, unlocking maximum hardware KV-cache reuse.",
    bulletPoints: [
      "Sub-millisecond SHA-256 deterministic prefix fingerprinting",
      "Maximizes prompt caching on Anthropic, OpenAI & self-hosted vLLM/SGLang",
      "Reduces TTFT (Time To First Token) from 850ms down to ~65ms",
      "Zero coordination bottleneck across multi-tenant gateway instances",
    ],
    visualType: "kv",
  },
  {
    id: "sentinel",
    name: "Sentinel Circuit Breakers",
    badge: "Fail-Safe State Machine",
    badgeColor: "text-amber-400 border-amber-800 bg-amber-950/60",
    icon: ShieldAlert,
    headline: "Automated CLOSED → OPEN → HALF-OPEN Resilience Without Cascading Outages",
    description:
      "When upstream providers return HTTP 5xx errors or 429 rate limits, VeloRoute trips the circuit breaker for that specific key. It applies exponential cooldown with randomized jitter, probes with half-open canary requests, and auto-disables revoked 401 keys without taking down your entire pool.",
    bulletPoints: [
      "3-state deterministic health machine (CLOSED, OPEN, HALF_OPEN)",
      "Exponential backoff with full randomized jitter prevents thundering herd",
      "Automatic 401 Unauthorized dead-key deactivation preserves cluster health",
      "Per-key error rate tracking with sub-millisecond failover to standby keys",
    ],
    visualType: "sentinel",
  },
  {
    id: "hedging",
    name: "Speculative Hedging",
    badge: "Parallel Low-Latency Race",
    badgeColor: "text-emerald-400 border-emerald-800 bg-emerald-950/60",
    icon: Zap,
    headline: "Dispatch Parallel Speculative Requests & Cancel Losers in Microseconds",
    description:
      "For SLA-critical agent and trading workflows, `/hedge` dispatches parallel requests to the two fastest candidate providers simultaneously. The moment the first chunk arrives from the leader, the lagging connection is aborted cleanly, eliminating long-tail latency spikes.",
    bulletPoints: [
      "Sub-millisecond parallel request spawning across diverse providers",
      "Immediate socket-level cancellation of lagging candidate on first token",
      "Cuts p99 latency spikes by up to 68% during cloud provider hiccups",
      "Controlled hedging budgets prevent runaway API spending",
    ],
    visualType: "hedging",
  },
  {
    id: "quality",
    name: "Complexity & Quality Router",
    badge: "Deterministic Tiering",
    badgeColor: "text-purple-400 border-purple-800 bg-purple-950/60",
    icon: Cpu,
    headline: "Route Trivial Prompts to Cheap Models & Hard Reasoning to Frontier Flags",
    description:
      "A zero-heavy-ML deterministic classifier evaluates semantic prompt indicators (reasoning tokens, math symbols, code syntax, length). Simple greetings and extraction queries go to sub-cent engines; multi-step algorithmic prompts are upgraded to o1, Claude 3.5 Sonnet, or DeepSeek-R1.",
    bulletPoints: [
      "Zero heavy ML runtimes: 0.05ms regex & token entropy classifier",
      "Automatic budget preservation: saves up to 85% by demoting trivial queries",
      "Configurable slash directives: override with /fast, /cheap, /reason, /smart",
      "EMA (Exponential Moving Average) quality tracking based on user feedback",
    ],
    visualType: "quality",
  },
  {
    id: "privacy",
    name: "Zero-Retention Privacy Guard",
    badge: "Shannon Entropy Shield",
    badgeColor: "text-teal-400 border-teal-800 bg-teal-950/60",
    icon: Lock,
    headline: "Tier-0 Deterministic Secret Redaction & Lossless Response Unmasking",
    description:
      "VeloRoute intercepts outbound prompts, identifies high-entropy strings (API keys, RSA keys, AWS secrets) using Shannon entropy and regex rules, and replaces them with reversible vault tokens before sending to third-party LLMs. When the model responds, tokens are restored losslessly.",
    bulletPoints: [
      "No prompt data ever persisted to cloud servers or third-party vector databases",
      "Deterministic Shannon entropy filter catches raw secrets before transit",
      "Lossless bidirectional token substitution: model never sees your production keys",
      "Compliance-ready for HIPAA, SOC-2, and GDPR air-gapped environments",
    ],
    visualType: "privacy",
  },
  {
    id: "mcp",
    name: "Universal MCP Gateway",
    badge: "Stdio to SSE Proxy",
    badgeColor: "text-rose-400 border-rose-800 bg-rose-950/60",
    icon: Network,
    headline: "Native Model Context Protocol Bridge with RTK Output Token Compression",
    description:
      "VeloRoute bridges local stdio MCP servers and distributed HTTP/SSE MCP endpoints into a single unified catalog. It automatically filters, compresses, and sanitizes tool payloads using RTK trimming before feeding them into LLM context windows.",
    bulletPoints: [
      "Full stdio & SSE transport support with dynamic tool registration",
      "RTK (Reduced Token Kit) output compressor trims bulky JSON payloads",
      "Automated MCP security posture scoring (audits tool privilege levels)",
      "Seamless integration with Claude Desktop, Cursor, and autonomous agent loops",
    ],
    visualType: "mcp",
  },
];

export default function ArchitectureTabs() {
  const [activeTab, setActiveTab] = useState<string>("kv_affinity");

  const current = STRATEGIES.find((s) => s.id === activeTab) || STRATEGIES[0];

  return (
    <section id="architecture" className="py-24 relative border-t border-white/5">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="text-center max-w-3xl mx-auto mb-16">
          <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-sky-950/60 border border-sky-500/30 text-sky-400 text-xs font-mono mb-4">
            <Activity className="w-3.5 h-3.5" />
            <span>High-Availability Routing & Resilience</span>
          </div>
          <h2 className="text-3xl sm:text-5xl font-extrabold text-white tracking-tight">
            Engineered for Pure Production Uptime.
          </h2>
          <p className="mt-4 text-slate-400 text-base sm:text-lg">
            No single point of failure. Explore how VeloRoute handles caching, failovers, parallel
            hedging, and enterprise zero-trust guardrails.
          </p>
        </div>

        {/* Strategy Selector Tabs */}
        <div className="flex items-center justify-start sm:justify-center overflow-x-auto pb-4 gap-2 mb-10 no-scrollbar">
          {STRATEGIES.map((s) => {
            const Icon = s.icon;
            const isActive = s.id === activeTab;
            return (
              <button
                key={s.id}
                onClick={() => setActiveTab(s.id)}
                className={`flex items-center space-x-2 px-4 py-2.5 rounded-xl text-xs sm:text-sm font-medium transition whitespace-nowrap border shrink-0 ${
                  isActive
                    ? "bg-slate-800 text-white border-sky-400/80 shadow-lg shadow-sky-500/10"
                    : "bg-slate-900/60 text-slate-400 border-white/5 hover:border-white/20 hover:text-slate-200"
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? "text-sky-400" : "text-slate-500"}`} />
                <span>{s.name}</span>
              </button>
            );
          })}
        </div>

        {/* Active Strategy Detail View */}
        <div className="glass-panel rounded-3xl border border-white/10 p-6 sm:p-10 shadow-2xl">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 items-center">
            {/* Left Content (6 cols) */}
            <div className="lg:col-span-6 space-y-6">
              <div className="inline-flex items-center px-3 py-1 rounded-full text-xs font-mono border">
                <span className={current.badgeColor}>{current.badge}</span>
              </div>

              <h3 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight leading-snug">
                {current.headline}
              </h3>

              <p className="text-slate-300 text-sm sm:text-base leading-relaxed">
                {current.description}
              </p>

              <div className="space-y-3 pt-2">
                {current.bulletPoints.map((pt, idx) => (
                  <div key={idx} className="flex items-start space-x-3 text-xs sm:text-sm text-slate-300">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                    <span>{pt}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Right Interactive Diagram (6 cols) */}
            <div className="lg:col-span-6">
              <div className="bg-[#080c14] border border-white/10 rounded-2xl p-6 sm:p-8 font-mono text-xs shadow-inner">
                {/* Visualizer Header */}
                <div className="flex items-center justify-between pb-4 mb-6 border-b border-white/10">
                  <span className="text-slate-400 flex items-center space-x-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping" />
                    <span>State Architecture // {current.id}</span>
                  </span>
                  <span className="text-sky-400 font-mono text-[11px]">ACTIVE ENGINE</span>
                </div>

                {/* Diagrams tailored to strategy */}
                {current.visualType === "kv" && (
                  <div className="space-y-4">
                    <div className="p-3.5 rounded-xl bg-slate-900 border border-sky-500/30 flex items-center justify-between">
                      <div>
                        <div className="text-[11px] text-sky-400 font-bold">Inbound System Prompt</div>
                        <div className="text-slate-400 text-[10px]">42,000 token codebase AST</div>
                      </div>
                      <div className="text-right">
                        <div className="text-amber-400 font-bold text-[10px]">SHA-256 Hash</div>
                        <div className="text-slate-500 text-[10px]">0x7c49...e2a</div>
                      </div>
                    </div>

                    <div className="flex justify-center my-2">
                      <div className="w-0.5 h-6 bg-gradient-to-b from-sky-400 to-emerald-400" />
                    </div>

                    <div className="p-4 rounded-xl bg-slate-900 border border-emerald-500/40">
                      <div className="text-emerald-400 font-bold text-xs mb-1">
                        🎯 Affinity Worker Node [GPU-02]
                      </div>
                      <div className="text-slate-300 text-[11px] mb-2">
                        KV Prefix Cache Status: <strong className="text-emerald-300">WARM (HIT)</strong>
                      </div>
                      <div className="w-full bg-slate-800 rounded-full h-2 mb-2">
                        <div className="bg-emerald-400 h-2 rounded-full w-[94%]" />
                      </div>
                      <div className="flex justify-between text-[10px] text-slate-400">
                        <span>Cache Reuse: 94%</span>
                        <span className="text-emerald-300 font-bold">Input Cost: -80%</span>
                      </div>
                    </div>
                  </div>
                )}

                {current.visualType === "sentinel" && (
                  <div className="space-y-4">
                    <div className="grid grid-cols-3 gap-2 text-center text-[10px]">
                      <div className="p-2.5 rounded-lg bg-emerald-950/40 border border-emerald-500/40 text-emerald-400">
                        <div className="font-bold">CLOSED</div>
                        <div className="text-slate-400 text-[9px] mt-1">Normal Traffic</div>
                      </div>
                      <div className="p-2.5 rounded-lg bg-rose-950/40 border border-rose-500/40 text-rose-400">
                        <div className="font-bold">OPEN</div>
                        <div className="text-slate-400 text-[9px] mt-1">Cooldown 30s-600s</div>
                      </div>
                      <div className="p-2.5 rounded-lg bg-amber-950/40 border border-amber-500/40 text-amber-400">
                        <div className="font-bold">HALF-OPEN</div>
                        <div className="text-slate-400 text-[9px] mt-1">Canary Probe</div>
                      </div>
                    </div>

                    <div className="p-3.5 rounded-xl bg-slate-900/90 border border-white/5 space-y-2 text-[11px]">
                      <div className="flex justify-between text-slate-300">
                        <span>Consecutive Error Threshold:</span>
                        <span className="text-amber-400 font-bold">5 failures</span>
                      </div>
                      <div className="flex justify-between text-slate-300">
                        <span>Backoff Strategy:</span>
                        <span className="text-sky-400">Exponential + Jitter</span>
                      </div>
                      <div className="flex justify-between text-slate-300">
                        <span>Auto-Revoke on HTTP 401:</span>
                        <span className="text-emerald-400 font-bold">Immediate</span>
                      </div>
                    </div>
                  </div>
                )}

                {current.visualType === "hedging" && (
                  <div className="space-y-3">
                    <div className="p-3 rounded-lg bg-slate-900 border border-sky-500/30">
                      <div className="flex justify-between items-center text-[11px]">
                        <span className="text-sky-300 font-bold">Speculative Fork 1 (Groq)</span>
                        <span className="text-emerald-400 font-bold">WINNER (142ms)</span>
                      </div>
                      <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2">
                        <div className="bg-emerald-400 h-1.5 rounded-full w-full" />
                      </div>
                    </div>

                    <div className="p-3 rounded-lg bg-slate-900 border border-white/5 opacity-60">
                      <div className="flex justify-between items-center text-[11px]">
                        <span className="text-slate-300">Speculative Fork 2 (Claude)</span>
                        <span className="text-rose-400 font-bold">CANCELLED (at 143ms)</span>
                      </div>
                      <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2">
                        <div className="bg-rose-400 h-1.5 rounded-full w-1/3" />
                      </div>
                    </div>

                    <div className="p-2.5 rounded-lg bg-sky-950/40 border border-sky-800/40 text-[10px] text-sky-300">
                      ⚡ <strong>Result:</strong> Zero trailing p99 tail latency. Sockets aborted
                      instantly, preventing duplicate billing.
                    </div>
                  </div>
                )}

                {current.visualType === "quality" && (
                  <div className="space-y-3">
                    <div className="p-3 rounded-lg bg-slate-900 border border-white/5 flex items-center justify-between text-[11px]">
                      <div>
                        <div className="text-slate-300">Prompt: "Summarize this 1-line log"</div>
                        <div className="text-slate-500 text-[10px]">Classifier score: 0.12 (Trivial)</div>
                      </div>
                      <span className="text-emerald-400 font-bold">→ gpt-4o-mini ($0.15/M)</span>
                    </div>

                    <div className="p-3 rounded-lg bg-slate-900 border border-purple-500/30 flex items-center justify-between text-[11px]">
                      <div>
                        <div className="text-slate-300">Prompt: "Formal verification of zk-STARK"</div>
                        <div className="text-slate-500 text-[10px]">Classifier score: 0.96 (Deep Reasoning)</div>
                      </div>
                      <span className="text-purple-400 font-bold">→ o1 / claude-3-5-sonnet</span>
                    </div>

                    <div className="p-2.5 rounded-lg bg-purple-950/40 border border-purple-800/40 text-[10px] text-purple-300">
                      💰 <strong>Outcome:</strong> 85% cost saving without compromising output quality on
                      complex logic.
                    </div>
                  </div>
                )}

                {current.visualType === "privacy" && (
                  <div className="space-y-3">
                    <div className="p-3 rounded-lg bg-slate-900 border border-rose-500/20 text-[11px]">
                      <div className="text-rose-400 font-bold mb-1">Inbound (Local Client)</div>
                      <div className="text-slate-300">"Deploy with AWS_KEY=AKIAIOSFODNN7EXAMPLE"</div>
                    </div>

                    <div className="flex justify-center">
                      <div className="text-[10px] text-teal-400 bg-teal-950/60 px-2 py-0.5 rounded border border-teal-800">
                        Shannon Entropy Filter (H &gt; 4.2)
                      </div>
                    </div>

                    <div className="p-3 rounded-lg bg-slate-900 border border-emerald-500/30 text-[11px]">
                      <div className="text-emerald-400 font-bold mb-1">Transmitted to Cloud LLM</div>
                      <div className="text-slate-300">"Deploy with AWS_KEY=__VELO_VAULT_TOKEN_01__"</div>
                    </div>
                  </div>
                )}

                {current.visualType === "mcp" && (
                  <div className="space-y-3 text-[11px]">
                    <div className="p-3 rounded-lg bg-slate-900 border border-sky-500/20 flex items-center justify-between">
                      <span className="text-sky-300">mcp-server-filesystem (stdio)</span>
                      <span className="text-emerald-400 font-mono">RTK -62%</span>
                    </div>
                    <div className="p-3 rounded-lg bg-slate-900 border border-sky-500/20 flex items-center justify-between">
                      <span className="text-sky-300">mcp-server-database (SSE)</span>
                      <span className="text-emerald-400 font-mono">RTK -71%</span>
                    </div>
                    <div className="p-2.5 rounded-lg bg-slate-950 border border-white/5 text-[10px] text-slate-400">
                      Unified under standard OpenAI / Anthropic tool-calling protocol.
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
