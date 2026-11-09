"use client";

import { useState } from "react";
import {
  LucideIcon,
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
  icon: LucideIcon;
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
  const [sentinelState, setSentinelState] = useState<"CLOSED" | "OPEN" | "HALF_OPEN">("CLOSED");

  const current = STRATEGIES.find((s) => s.id === activeTab) || STRATEGIES[0];

  return (
    <section id="architecture" className="py-24 relative border-t border-[#18181C] bg-[#000000]">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-8 lg:px-[120px]">
        {/* Header */}
        <div className="text-center max-w-3xl mx-auto mb-16">
          <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-none bg-[#111114] border border-[#18181C] text-[#0055FF] text-[11px] font-mono uppercase tracking-widest mb-4">
            <Activity className="w-3.5 h-3.5 text-[#0055FF]" />
            <span>ROUTING ARCHITECTURE & RESILIENCE</span>
          </div>
          <h2 className="text-3xl sm:text-5xl font-bold text-[#FBFBFF] tracking-tight">
            Engineered for Pure Production Uptime.
          </h2>
          <p className="mt-4 text-[#A7A9B8] text-base sm:text-lg">
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
                className={`flex items-center space-x-2 px-4 py-2.5 rounded-none text-xs font-mono uppercase tracking-wider transition whitespace-nowrap border shrink-0 ${
                  isActive
                    ? "bg-[#0055FF] text-[#FBFBFF] border-[#0055FF]"
                    : "bg-[#0B0B0D] text-[#A7A9B8] border-[#18181C] hover:border-white/20 hover:text-[#FBFBFF]"
                }`}
              >
                <Icon className={`w-3.5 h-3.5 ${isActive ? "text-[#FBFBFF]" : "text-[#5B5D6B]"}`} />
                <span>{s.name}</span>
              </button>
            );
          })}
        </div>

        {/* Active Strategy Detail View */}
        <div className="bg-[#0B0B0D] rounded-none border border-[#18181C] p-6 sm:p-10 shadow-none">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 items-center">
            {/* Left Content (6 cols) */}
            <div className="lg:col-span-6 space-y-6">
              <div className="inline-flex items-center px-3 py-1 rounded-none text-[11px] font-mono uppercase tracking-wider border border-[#18181C] bg-[#111114]">
                <span className="text-[#0055FF] font-bold">{current.badge}</span>
              </div>

              <h3 className="text-2xl sm:text-3xl font-bold text-[#FBFBFF] tracking-tight leading-snug">
                {current.headline}
              </h3>

              <p className="text-[#DFE0EA] text-sm sm:text-base leading-relaxed">
                {current.description}
              </p>

              <div className="space-y-3 pt-2">
                {current.bulletPoints.map((pt, idx) => (
                  <div key={idx} className="flex items-start space-x-3 text-xs sm:text-sm text-[#DFE0EA]">
                    <CheckCircle2 className="w-4 h-4 text-[#0055FF] shrink-0 mt-0.5" />
                    <span>{pt}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Right Interactive Diagram (6 cols) */}
            <div className="lg:col-span-6">
              <div className="bg-[#000000] border border-[#18181C] rounded-none p-6 sm:p-8 font-mono text-xs">
                {/* Visualizer Header */}
                <div className="flex items-center justify-between pb-4 mb-6 border-b border-[#18181C]">
                  <span className="text-[#A7A9B8] flex items-center space-x-2 uppercase tracking-wider text-[11px]">
                    <span className="w-2 h-2 rounded-none bg-[#0055FF]" />
                    <span>State Architecture // {current.id}</span>
                  </span>
                  <span className="text-[#0055FF] font-mono text-[10px] uppercase tracking-widest font-bold">ACTIVE ENGINE</span>
                </div>

                {/* Diagrams tailored to strategy */}
                {current.visualType === "kv" && (
                  <div className="space-y-4">
                    <div className="p-3.5 rounded-none bg-[#0B0B0D] border border-[#18181C] flex items-center justify-between">
                      <div>
                        <div className="text-[11px] text-[#FBFBFF] font-bold uppercase tracking-wider">Inbound System Prompt</div>
                        <div className="text-[#A7A9B8] text-[10px]">42,000 token codebase AST</div>
                      </div>
                      <div className="text-right">
                        <div className="text-[#0055FF] font-bold text-[10px]">SHA-256 Hash</div>
                        <div className="text-[#5B5D6B] text-[10px]">0x7c49...e2a</div>
                      </div>
                    </div>

                    <div className="flex justify-center my-2">
                      <div className="w-0.5 h-6 bg-[#0055FF]" />
                    </div>

                    <div className="p-4 rounded-none bg-[#0B0B0D] border border-[#0055FF]/40">
                      <div className="text-[#0055FF] font-bold text-xs mb-1 uppercase tracking-wider">
                        Affinity Worker Node [GPU-02]
                      </div>
                      <div className="text-[#DFE0EA] text-[11px] mb-2">
                        KV Prefix Cache Status: <strong className="text-[#FBFBFF]">WARM (HIT)</strong>
                      </div>
                      <div className="w-full bg-[#18181C] rounded-none h-2 mb-2">
                        <div className="bg-[#0055FF] h-2 rounded-none w-[94%]" />
                      </div>
                      <div className="flex justify-between text-[10px] text-[#A7A9B8]">
                        <span>Cache Reuse: 94%</span>
                        <span className="text-[#FBFBFF] font-bold">Input Cost: -80%</span>
                      </div>
                    </div>
                  </div>
                )}

                {current.visualType === "sentinel" && (
                  <div className="space-y-4">
                    <div className="grid grid-cols-3 gap-2 text-center text-[10px]">
                      <button
                        onClick={() => setSentinelState("CLOSED")}
                        className={`p-2.5 rounded-none border transition ${
                          sentinelState === "CLOSED"
                            ? "bg-[#111114] border-[#0055FF] text-[#FBFBFF] font-bold"
                            : "bg-[#0B0B0D] border-[#18181C] text-[#A7A9B8] hover:border-white/20"
                        }`}
                      >
                        <div className="font-bold flex items-center justify-center space-x-1">
                          {sentinelState === "CLOSED" && <span className="w-1.5 h-1.5 rounded-none bg-[#0055FF]" />}
                          <span>CLOSED</span>
                        </div>
                        <div className="text-[#5B5D6B] text-[9px] mt-1 uppercase">Normal Traffic</div>
                      </button>
                      <button
                        onClick={() => setSentinelState("OPEN")}
                        className={`p-2.5 rounded-none border transition ${
                          sentinelState === "OPEN"
                            ? "bg-[#111114] border-white text-white font-bold"
                            : "bg-[#0B0B0D] border-[#18181C] text-[#A7A9B8] hover:border-white/20"
                        }`}
                      >
                        <div className="font-bold flex items-center justify-center space-x-1">
                          {sentinelState === "OPEN" && <span className="w-1.5 h-1.5 rounded-none bg-white" />}
                          <span>OPEN</span>
                        </div>
                        <div className="text-[#5B5D6B] text-[9px] mt-1 uppercase">Cooldown Active</div>
                      </button>
                      <button
                        onClick={() => setSentinelState("HALF_OPEN")}
                        className={`p-2.5 rounded-none border transition ${
                          sentinelState === "HALF_OPEN"
                            ? "bg-[#111114] border-[#0055FF] text-[#0055FF] font-bold"
                            : "bg-[#0B0B0D] border-[#18181C] text-[#A7A9B8] hover:border-white/20"
                        }`}
                      >
                        <div className="font-bold flex items-center justify-center space-x-1">
                          {sentinelState === "HALF_OPEN" && <span className="w-1.5 h-1.5 rounded-none bg-[#0055FF]" />}
                          <span>HALF-OPEN</span>
                        </div>
                        <div className="text-[#5B5D6B] text-[9px] mt-1 uppercase">Canary Probe</div>
                      </button>
                    </div>

                    {/* Interactive Simulator Bar */}
                    <div className="flex items-center justify-between p-2.5 rounded-none bg-[#0B0B0D] border border-[#18181C] text-[11px]">
                      <span className="text-[#A7A9B8] uppercase text-[10px]">Simulate Action:</span>
                      <div className="flex space-x-1.5">
                        <button
                          onClick={() => setSentinelState("OPEN")}
                          className="px-2 py-0.5 rounded-none bg-[#111114] text-[#FBFBFF] border border-[#18181C] hover:border-white/30 text-[10px] font-mono transition uppercase"
                        >
                          + 429 Trip
                        </button>
                        <button
                          onClick={() => setSentinelState("HALF_OPEN")}
                          className="px-2 py-0.5 rounded-none bg-[#111114] text-[#0055FF] border border-[#18181C] hover:border-white/30 text-[10px] font-mono transition uppercase"
                        >
                          Probe Canary
                        </button>
                        <button
                          onClick={() => setSentinelState("CLOSED")}
                          className="px-2 py-0.5 rounded-none bg-[#0055FF] text-[#FBFBFF] hover:bg-[#0044CC] text-[10px] font-mono transition uppercase"
                        >
                          Recover
                        </button>
                      </div>
                    </div>

                    <div className="p-3.5 rounded-none bg-[#0B0B0D] border border-[#18181C] space-y-2 text-[11px]">
                      <div className="flex justify-between text-[#DFE0EA]">
                        <span>Current State Status:</span>
                        <span className={`font-bold font-mono ${
                          sentinelState === "CLOSED"
                            ? "text-[#0055FF]"
                            : sentinelState === "OPEN"
                            ? "text-white"
                            : "text-[#DFE0EA]"
                        }`}>
                          {sentinelState === "CLOSED" && "Healthy (Key pool accepting 100% traffic)"}
                          {sentinelState === "OPEN" && "Tripped (Backoff: 30.0s cooldown + jitter)"}
                          {sentinelState === "HALF_OPEN" && "Canary in flight (1 probe request allowed)"}
                        </span>
                      </div>
                      <div className="flex justify-between text-[#DFE0EA]">
                        <span>Consecutive Error Threshold:</span>
                        <span className="text-[#FBFBFF] font-bold">5 failures</span>
                      </div>
                      <div className="flex justify-between text-[#DFE0EA]">
                        <span>Backoff Strategy:</span>
                        <span className="text-[#0055FF]">Exponential + Jitter</span>
                      </div>
                      <div className="flex justify-between text-[#DFE0EA]">
                        <span>Auto-Revoke on HTTP 401:</span>
                        <span className="text-[#FBFBFF] font-bold">Immediate</span>
                      </div>
                    </div>
                  </div>
                )}

                {current.visualType === "hedging" && (
                  <div className="space-y-3">
                    <div className="p-3 rounded-none bg-[#0B0B0D] border border-[#0055FF]/40">
                      <div className="flex justify-between items-center text-[11px]">
                        <span className="text-[#FBFBFF] font-bold">Speculative Fork 1 (Groq)</span>
                        <span className="text-[#0055FF] font-bold">WINNER (142ms)</span>
                      </div>
                      <div className="w-full bg-[#18181C] h-1.5 rounded-none mt-2">
                        <div className="bg-[#0055FF] h-1.5 rounded-none w-full" />
                      </div>
                    </div>

                    <div className="p-3 rounded-none bg-[#0B0B0D] border border-[#18181C] opacity-60">
                      <div className="flex justify-between items-center text-[11px]">
                        <span className="text-[#A7A9B8]">Speculative Fork 2 (Claude)</span>
                        <span className="text-[#5B5D6B] font-bold">CANCELLED (at 143ms)</span>
                      </div>
                      <div className="w-full bg-[#18181C] h-1.5 rounded-none mt-2">
                        <div className="bg-[#5B5D6B] h-1.5 rounded-none w-1/3" />
                      </div>
                    </div>

                    <div className="p-2.5 rounded-none bg-[#111114] border border-[#18181C] text-[10px] text-[#DFE0EA]">
                      ⚡ <strong>Result:</strong> Zero trailing p99 tail latency. Sockets aborted
                      instantly, preventing duplicate billing.
                    </div>
                  </div>
                )}

                {current.visualType === "quality" && (
                  <div className="space-y-3">
                    <div className="p-3 rounded-none bg-[#0B0B0D] border border-[#18181C] flex items-center justify-between text-[11px]">
                      <div>
                        <div className="text-[#DFE0EA]">Prompt: &quot;Summarize this 1-line log&quot;</div>
                        <div className="text-[#5B5D6B] text-[10px]">Classifier score: 0.12 (Trivial)</div>
                      </div>
                      <span className="text-[#0055FF] font-bold">→ gpt-4o-mini ($0.15/M)</span>
                    </div>

                    <div className="p-3 rounded-none bg-[#0B0B0D] border border-[#0055FF]/40 flex items-center justify-between text-[11px]">
                      <div>
                        <div className="text-[#FBFBFF]">Prompt: &quot;Formal verification of zk-STARK&quot;</div>
                        <div className="text-[#5B5D6B] text-[10px]">Classifier score: 0.96 (Deep Reasoning)</div>
                      </div>
                      <span className="text-[#FBFBFF] font-bold">→ o1 / claude-3-5-sonnet</span>
                    </div>

                    <div className="p-2.5 rounded-none bg-[#111114] border border-[#18181C] text-[10px] text-[#DFE0EA]">
                      💰 <strong>Outcome:</strong> 85% cost saving without compromising output quality on
                      complex logic.
                    </div>
                  </div>
                )}

                {current.visualType === "privacy" && (
                  <div className="space-y-3">
                    <div className="p-3 rounded-none bg-[#0B0B0D] border border-[#18181C] text-[11px]">
                      <div className="text-[#A7A9B8] font-bold mb-1 uppercase tracking-wider text-[10px]">Inbound (Local Client)</div>
                      <div className="text-[#DFE0EA]">&quot;Deploy with AWS_KEY=AKIAIOSFODNN7EXAMPLE&quot;</div>
                    </div>

                    <div className="flex justify-center">
                      <div className="text-[10px] text-[#FBFBFF] bg-[#18181C] px-2 py-0.5 rounded-none border border-[#18181C] uppercase tracking-wider">
                        Shannon Entropy Filter (H &gt; 4.2)
                      </div>
                    </div>

                    <div className="p-3 rounded-none bg-[#0B0B0D] border border-[#0055FF]/40 text-[11px]">
                      <div className="text-[#0055FF] font-bold mb-1 uppercase tracking-wider text-[10px]">Transmitted to Cloud LLM</div>
                      <div className="text-[#FBFBFF]">&quot;Deploy with AWS_KEY=__VELO_VAULT_TOKEN_01__&quot;</div>
                    </div>
                  </div>
                )}

                {current.visualType === "mcp" && (
                  <div className="space-y-3 text-[11px]">
                    <div className="p-3 rounded-none bg-[#0B0B0D] border border-[#18181C] flex items-center justify-between">
                      <span className="text-[#DFE0EA]">mcp-server-filesystem (stdio)</span>
                      <span className="text-[#0055FF] font-mono font-bold">RTK -62%</span>
                    </div>
                    <div className="p-3 rounded-none bg-[#0B0B0D] border border-[#18181C] flex items-center justify-between">
                      <span className="text-[#DFE0EA]">mcp-server-database (SSE)</span>
                      <span className="text-[#0055FF] font-mono font-bold">RTK -71%</span>
                    </div>
                    <div className="p-2.5 rounded-none bg-[#111114] border border-[#18181C] text-[10px] text-[#A7A9B8]">
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
