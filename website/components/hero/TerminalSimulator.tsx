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
    <div className="max-w-4xl mx-auto rounded-none bg-[#0B0B0D] shadow-none overflow-hidden border border-[#18181C]">
      {/* Terminal Title Bar */}
      <div className="flex flex-wrap items-center justify-between px-4 py-3 bg-[#000000] border-b border-[#18181C] gap-2">
        <div className="flex items-center space-x-2">
          <div className="w-2.5 h-2.5 rounded-none bg-[#5B5D6B]" />
          <div className="w-2.5 h-2.5 rounded-none bg-[#A7A9B8]" />
          <div className="w-2.5 h-2.5 rounded-none bg-[#0055FF]" />
          <span className="text-xs font-mono text-[#A7A9B8] ml-2 tracking-wide uppercase">
            veloroute-gateway // live-stream-trace
          </span>
        </div>
        <div className="flex items-center space-x-1.5">
          <button
            onClick={triggerSimulation}
            className="flex items-center space-x-1 px-2.5 py-1 rounded-none text-[10px] font-mono uppercase tracking-wider text-[#FBFBFF] bg-[#111114] hover:bg-[#18181C] border border-[#18181C] transition"
            title="Simulate incoming request trace"
          >
            <RotateCcw className={`w-3 h-3 ${isSimulating ? "animate-spin" : ""}`} />
            <span>Re-simulate</span>
          </button>
          <button
            onClick={() => setActiveTab("stream")}
            className={`px-2.5 py-1 rounded-none text-[10px] font-mono uppercase tracking-wider transition ${
              activeTab === "stream"
                ? "bg-[#0055FF] text-[#FBFBFF]"
                : "text-[#A7A9B8] hover:text-[#FBFBFF]"
            }`}
          >
            /v1/chat/completions
          </button>
          <button
            onClick={() => setActiveTab("resilience")}
            className={`px-2.5 py-1 rounded-none text-[10px] font-mono uppercase tracking-wider transition ${
              activeTab === "resilience"
                ? "bg-[#0055FF] text-[#FBFBFF]"
                : "text-[#A7A9B8] hover:text-[#FBFBFF]"
            }`}
          >
            Sentinel Failover
          </button>
          <button
            onClick={() => setActiveTab("kv")}
            className={`px-2.5 py-1 rounded-none text-[10px] font-mono uppercase tracking-wider transition ${
              activeTab === "kv"
                ? "bg-[#0055FF] text-[#FBFBFF]"
                : "text-[#A7A9B8] hover:text-[#FBFBFF]"
            }`}
          >
            KV-Prefix Affinity
          </button>
        </div>
      </div>

      {/* Terminal Body */}
      <div className="p-5 font-mono text-xs sm:text-sm bg-[#0B0B0D] text-[#DFE0EA] leading-relaxed overflow-x-auto min-h-[220px]">
        {isSimulating && (
          <div className="py-2 px-3 mb-3 rounded-none bg-[#111114] border border-[#0055FF] text-[#0055FF] font-mono text-xs flex items-center space-x-2">
            <span className="w-2 h-2 rounded-none bg-[#0055FF] animate-ping" />
            <span className="uppercase tracking-wider">[GATEWAY PROXY] Ingesting request, scrubbing Shannon entropy secrets, computing KV fingerprint...</span>
          </div>
        )}
        {activeTab === "stream" && (
          <div className="space-y-1.5 animate-fadeIn">
            <p className="text-[#5B5D6B]"># Inbound request to unified gateway port 8000</p>
            <p>
              <span className="text-[#0055FF] font-bold">POST</span> /v1/chat/completions{" "}
              <span className="text-[#FBFBFF] font-semibold">[200 OK]</span> in{" "}
              <span className="text-[#DFE0EA]">142ms</span>
            </p>
            <p className="text-[#A7A9B8]">
              <span className="text-[#5B5D6B]">├─</span> Routing Engine:{" "}
              <span className="text-[#FBFBFF] font-bold">smart</span> (classified as &apos;reasoning&apos; query)
            </p>
            <p className="text-[#A7A9B8]">
              <span className="text-[#5B5D6B]">├─</span> Selected Provider:{" "}
              <span className="text-[#0055FF]">anthropic/claude-3-5-sonnet</span> via healthy key pool #2
            </p>
            <p className="text-[#A7A9B8]">
              <span className="text-[#5B5D6B]">├─</span> Token-Saviour:{" "}
              <span className="text-[#DFE0EA]">AST Skeletonizer</span> compressed context from{" "}
              <span className="line-through text-[#5B5D6B]">8,420</span> to{" "}
              <span className="text-[#FBFBFF] font-bold">2,110 tokens</span> (-74.9%)
            </p>
            <p className="text-[#A7A9B8]">
              <span className="text-[#5B5D6B]">├─</span> Guardrail:{" "}
              <span className="text-[#DFE0EA]">Shannon entropy scrubber</span> redacted 2 API keys &amp; unmasked on response
            </p>
            <p className="text-[#FBFBFF] font-semibold">
              <span className="text-[#5B5D6B]">└─</span> Stream chunks delivered: 418 tokens at 94.2 tok/sec
            </p>
          </div>
        )}

        {activeTab === "resilience" && (
          <div className="space-y-1.5 animate-fadeIn">
            <p className="text-[#5B5D6B]"># Primary backend encountered 429 Rate Limit</p>
            <p className="text-[#A7A9B8]">
              [12:04:19] WARN: openai (key #1) returned HTTP 429 Too Many Requests
            </p>
            <p className="text-[#FBFBFF] font-bold">
              [12:04:19] SENTINEL: Trip circuit breaker for key #1. Exponential cooldown: 30.0s (trip #1)
            </p>
            <p className="text-[#0055FF] font-semibold">
              [12:04:19] RESILIENCE: Mid-stream failover to groq/llama-3.3-70b (sub-millisecond swap)
            </p>
            <p className="text-[#FBFBFF] font-semibold">
              [12:04:20] SUCCESS: Stream resumed at byte offset 124 without client interruption! (Status: 200)
            </p>
          </div>
        )}

        {activeTab === "kv" && (
          <div className="space-y-1.5 animate-fadeIn">
            <p className="text-[#5B5D6B]"># Large system prompt &amp; codebase context detected</p>
            <p className="text-[#0055FF]">
              [12:05:01] KV-AFFINITY: Computing SHA-256 fingerprint for 45,000-token system prefix...
            </p>
            <p className="text-[#DFE0EA]">
              [12:05:01] HASH: <span className="text-[#FBFBFF] font-mono">e8f49b2c...a07</span> pinned to worker node-04
            </p>
            <p className="text-[#FBFBFF] font-bold">
              [12:05:01] PROMPT CACHE HIT: 100% KV prefix reuse on vLLM/Anthropic cluster!
            </p>
            <p className="text-[#A7A9B8]">
              [12:05:01] BILLING: Input token fee dropped by 80.0% ($0.032 -&gt; $0.0064). TTFT: 48ms.
            </p>
          </div>
        )}
      </div>

      {/* Terminal Footer Status Bar */}
      <div className="px-4 py-2.5 bg-[#000000] text-[10px] font-mono text-[#A7A9B8] flex flex-wrap items-center justify-between border-t border-[#18181C] gap-2 uppercase tracking-wider">
        <div className="flex items-center space-x-3">
          <span className="flex items-center space-x-1.5">
            <span className="w-1.5 h-1.5 rounded-none bg-[#0055FF]" />
            <span>Gateway Status: Operational</span>
          </span>
          <span className="text-[#5B5D6B]">•</span>
          <span className="text-[#0055FF]">Overhead: 0.72ms</span>
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
