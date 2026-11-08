"use client";

import { useState } from "react";
import { RotateCcw } from "lucide-react";

export default function TerminalSimulator() {
  const [activeTab, setActiveTab] = useState<"stream" | "resilience" | "kv">("stream");
  const [isSimulating, setIsSimulating] = useState(false);

  const triggerSimulation = () => {
    setIsSimulating(true);
    setTimeout(() => setIsSimulating(false), 800);
  };

  return (
    <div className="max-w-4xl mx-auto rounded-2xl glass-panel shadow-2xl overflow-hidden border border-white/10">
      {/* Terminal Title Bar */}
      <div className="flex flex-wrap items-center justify-between px-4 py-3 bg-slate-950/80 border-b border-white/10 gap-2">
        <div className="flex items-center space-x-2">
          <div className="w-3 h-3 rounded-full bg-rose-500/80" />
          <div className="w-3 h-3 rounded-full bg-amber-500/80" />
          <div className="w-3 h-3 rounded-full bg-emerald-500/80" />
          <span className="text-xs font-mono text-slate-400 ml-2">
            veloroute-gateway :: live-proxy-stream
          </span>
        </div>
        <div className="flex items-center space-x-2">
          <button
            onClick={triggerSimulation}
            className="flex items-center space-x-1 px-2.5 py-1 rounded text-[11px] font-mono text-emerald-300 bg-emerald-950/50 hover:bg-emerald-900/60 border border-emerald-500/40 transition"
            title="Simulate incoming request trace"
          >
            <RotateCcw className={`w-3 h-3 ${isSimulating ? "animate-spin" : ""}`} />
            <span>Re-simulate</span>
          </button>
          <button
            onClick={() => setActiveTab("stream")}
            className={`px-2.5 py-1 rounded text-[11px] font-mono transition ${
              activeTab === "stream"
                ? "bg-sky-500/20 text-sky-300 border border-sky-500/40"
                : "text-slate-400 hover:text-white"
            }`}
          >
            /v1/chat/completions
          </button>
          <button
            onClick={() => setActiveTab("resilience")}
            className={`px-2.5 py-1 rounded text-[11px] font-mono transition ${
              activeTab === "resilience"
                ? "bg-sky-500/20 text-sky-300 border border-sky-500/40"
                : "text-slate-400 hover:text-white"
            }`}
          >
            Sentinel Failover
          </button>
          <button
            onClick={() => setActiveTab("kv")}
            className={`px-2.5 py-1 rounded text-[11px] font-mono transition ${
              activeTab === "kv"
                ? "bg-sky-500/20 text-sky-300 border border-sky-500/40"
                : "text-slate-400 hover:text-white"
            }`}
          >
            KV-Prefix Affinity
          </button>
        </div>
      </div>

      {/* Terminal Body */}
      <div className="p-5 font-mono text-xs sm:text-sm bg-[#080c14]/90 text-slate-300 leading-relaxed overflow-x-auto min-h-[220px]">
        {isSimulating && (
          <div className="py-2.5 px-3.5 mb-3 rounded-lg bg-sky-950/70 border border-sky-500/40 text-sky-300 font-mono text-xs flex items-center space-x-2 animate-pulse">
            <span className="w-2 h-2 rounded-full bg-sky-400 animate-ping" />
            <span>[GATEWAY PROXY] Ingesting request, scrubbing Shannon entropy secrets, computing KV fingerprint...</span>
          </div>
        )}
        {activeTab === "stream" && (
          <div className="space-y-1.5 animate-fadeIn">
            <p className="text-slate-500"># Inbound request to unified gateway port 8000</p>
            <p>
              <span className="text-sky-400 font-bold">POST</span> /v1/chat/completions{" "}
              <span className="text-emerald-400 font-semibold">[200 OK]</span> in{" "}
              <span className="text-amber-300">142ms</span>
            </p>
            <p className="text-slate-400">
              <span className="text-slate-500">├─</span> Routing Engine:{" "}
              <span className="text-sky-300 font-bold">smart</span> (classified as &apos;reasoning&apos; query)
            </p>
            <p className="text-slate-400">
              <span className="text-slate-500">├─</span> Selected Provider:{" "}
              <span className="text-emerald-400">anthropic/claude-3-5-sonnet</span> via healthy key pool #2
            </p>
            <p className="text-slate-400">
              <span className="text-slate-500">├─</span> Token-Saviour:{" "}
              <span className="text-teal-300">AST Skeletonizer</span> compressed context from{" "}
              <span className="line-through text-rose-400">8,420</span> to{" "}
              <span className="text-emerald-300 font-bold">2,110 tokens</span> (-74.9%)
            </p>
            <p className="text-slate-400">
              <span className="text-slate-500">├─</span> Guardrail:{" "}
              <span className="text-sky-300">Shannon entropy scrubber</span> redacted 2 API keys &amp; unmasked on response
            </p>
            <p className="text-emerald-400 font-semibold">
              <span className="text-slate-500">└─</span> Stream chunks delivered: 418 tokens at 94.2 tok/sec
            </p>
          </div>
        )}

        {activeTab === "resilience" && (
          <div className="space-y-1.5 animate-fadeIn">
            <p className="text-slate-500"># Primary backend encountered 429 Rate Limit</p>
            <p className="text-rose-400">
              [12:04:19] WARN: openai (key #1) returned HTTP 429 Too Many Requests
            </p>
            <p className="text-amber-300 font-bold">
              [12:04:19] SENTINEL: Trip circuit breaker for key #1. Exponential cooldown: 30.0s (trip #1)
            </p>
            <p className="text-sky-300 font-semibold">
              [12:04:19] RESILIENCE: Mid-stream failover to groq/llama-3.3-70b (sub-millisecond swap)
            </p>
            <p className="text-emerald-400 font-semibold">
              [12:04:20] SUCCESS: Stream resumed at byte offset 124 without client interruption! (Status: 200)
            </p>
          </div>
        )}

        {activeTab === "kv" && (
          <div className="space-y-1.5 animate-fadeIn">
            <p className="text-slate-500"># Large system prompt &amp; codebase context detected</p>
            <p className="text-sky-300">
              [12:05:01] KV-AFFINITY: Computing SHA-256 fingerprint for 45,000-token system prefix...
            </p>
            <p className="text-slate-300">
              [12:05:01] HASH: <span className="text-amber-400 font-mono">e8f49b2c...a07</span> pinned to worker node-04
            </p>
            <p className="text-emerald-400 font-bold">
              [12:05:01] PROMPT CACHE HIT: 100% KV prefix reuse on vLLM/Anthropic cluster!
            </p>
            <p className="text-teal-300">
              [12:05:01] BILLING: Input token fee dropped by 80.0% ($0.032 -&gt; $0.0064). TTFT: 48ms.
            </p>
          </div>
        )}
      </div>

      {/* Terminal Footer Status Bar */}
      <div className="px-4 py-2 bg-slate-950 text-[11px] font-mono text-slate-400 flex flex-wrap items-center justify-between border-t border-white/5 gap-2">
        <div className="flex items-center space-x-3">
          <span className="flex items-center space-x-1">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            <span>Gateway Status: Operational</span>
          </span>
          <span>•</span>
          <span className="text-sky-400">Overhead: 0.72ms</span>
        </div>
        <div className="flex items-center space-x-4">
          <span>Memory: ~34MB</span>
          <span>Active Keys: 12</span>
          <span>Circuit: All Closed</span>
        </div>
      </div>
    </div>
  );
}
