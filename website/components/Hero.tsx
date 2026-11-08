"use client";

import { useState, useEffect } from "react";
import {
  Copy,
  Check,
  Terminal,
  Zap,
  Shield,
  ArrowRight,
  Server,
  Cpu,
  Layers,
  Database,
  Lock,
  Play,
  RotateCcw,
} from "lucide-react";

export default function Hero() {
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState<"stream" | "resilience" | "kv">("stream");
  const [stars, setStars] = useState<number | null>(null);
  const [isSimulating, setIsSimulating] = useState(false);

  useEffect(() => {
    fetch("https://api.github.com/repos/mrgusux/veloroute")
      .then((res) => res.json())
      .then((data) => {
        if (data && typeof data.stargazers_count === "number") {
          setStars(data.stargazers_count);
        }
      })
      .catch(() => {});
  }, []);

  const triggerSimulation = () => {
    setIsSimulating(true);
    setTimeout(() => setIsSimulating(false), 800);
  };

  const dockerCommand =
    "docker run -d -p 8000:8000 -v veloroute_data:/data ghcr.io/mrgusux/veloroute:latest";

  const handleCopy = () => {
    navigator.clipboard.writeText(dockerCommand);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <section className="relative pt-32 pb-20 md:pt-40 md:pb-32 overflow-hidden">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        {/* Top Feature Pill */}
        <div className="flex justify-center mb-6">
          <div className="inline-flex items-center space-x-2 px-3.5 py-1.5 rounded-full bg-slate-900/90 border border-sky-500/30 text-xs text-slate-300 backdrop-blur-md shadow-inner shadow-sky-500/10 hover:border-sky-500/60 transition">
            <span className="flex h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="font-mono text-sky-400 font-semibold">VeloRoute v1.0</span>
            <span className="text-slate-500">•</span>
            <span>Sub-Millisecond Multi-Provider AI Gateway & Token Saviour</span>
            <ArrowRight className="w-3 h-3 text-slate-400" />
          </div>
        </div>

        {/* Main Headline */}
        <div className="text-center max-w-4xl mx-auto mb-8">
          <h1 className="text-4xl sm:text-6xl lg:text-7xl font-extrabold tracking-tight text-white leading-[1.1]">
            The Ultra-Fast AI Gateway with{" "}
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-sky-400 via-teal-300 to-emerald-400 glow-cyan">
              Zero Retention
            </span>{" "}
            & Native Token Savings.
          </h1>
          <p className="mt-6 text-lg sm:text-xl text-slate-300 max-w-2xl mx-auto font-normal leading-relaxed">
            Eliminate LLM outages with automated sentinel circuit breakers, speculative hedging,
            and AST context compression. Route effortlessly between OpenAI, Anthropic, Gemini, Groq,
            and local Ollama with <span className="text-sky-300 font-semibold font-mono">&lt; 0.8ms</span> overhead.
          </p>
        </div>

        {/* Action Buttons & 1-Command Docker Run */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-14">
          {/* Docker Run Copy Pill */}
          <div className="flex items-center bg-slate-950/90 border border-sky-500/40 hover:border-sky-400/80 rounded-xl p-1.5 backdrop-blur-lg shadow-xl shadow-sky-500/10 max-w-xl w-full sm:w-auto transition-all">
            <div className="flex items-center space-x-2 px-3 py-1.5 font-mono text-xs text-sky-300 select-all overflow-x-auto whitespace-nowrap">
              <span className="text-emerald-400 select-none">$</span>
              <span>{dockerCommand}</span>
            </div>
            <button
              onClick={handleCopy}
              className="flex items-center space-x-1.5 px-3 py-2 rounded-lg bg-sky-500/20 hover:bg-sky-500/30 text-sky-300 font-mono text-xs font-semibold border border-sky-500/30 transition shrink-0 ml-auto"
              title="Copy Docker command"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-emerald-400" />
                  <span className="text-emerald-400">Copied!</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  <span>Copy</span>
                </>
              )}
            </button>
          </div>

          <a
            href="https://github.com/mrgusux/veloroute"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center space-x-2.5 px-5 py-3 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-100 font-medium text-sm border border-white/10 hover:border-sky-500/40 transition shadow-lg shrink-0 group"
          >
            <span>Star on GitHub</span>
            <span className="text-amber-400 font-mono">★</span>
            <span className="px-2 py-0.5 rounded bg-slate-800 text-amber-300 font-mono text-xs border border-amber-500/30 group-hover:border-amber-400/60 transition">
              {stars !== null ? stars : "★"}
            </span>
          </a>
        </div>

        {/* Live Interactive Terminal Preview */}
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
                  <span className="text-sky-300 font-bold">smart</span> (classified as 'reasoning' query)
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
                  <span className="text-sky-300">Shannon entropy scrubber</span> redacted 2 API keys & unmasked on response
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
                <p className="text-slate-500"># Large system prompt & codebase context detected</p>
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

        {/* Enterprise Metrics Ribbon */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-12 max-w-5xl mx-auto">
          <div className="glass-panel p-5 rounded-xl border border-white/10 text-center">
            <div className="text-2xl sm:text-3xl font-extrabold text-sky-400 font-mono">&lt; 0.8ms</div>
            <div className="text-xs sm:text-sm text-slate-400 mt-1">Routing Overhead</div>
          </div>
          <div className="glass-panel p-5 rounded-xl border border-white/10 text-center">
            <div className="text-2xl sm:text-3xl font-extrabold text-emerald-400 font-mono">Up to 75%</div>
            <div className="text-xs sm:text-sm text-slate-400 mt-1">Context Cost Reduction</div>
          </div>
          <div className="glass-panel p-5 rounded-xl border border-white/10 text-center">
            <div className="text-2xl sm:text-3xl font-extrabold text-amber-400 font-mono">0 Outages</div>
            <div className="text-xs sm:text-sm text-slate-400 mt-1">Sentinel Auto-Failover</div>
          </div>
          <div className="glass-panel p-5 rounded-xl border border-white/10 text-center">
            <div className="text-2xl sm:text-3xl font-extrabold text-purple-400 font-mono">219 / 219</div>
            <div className="text-xs sm:text-sm text-slate-400 mt-1">Unit Tests Passing</div>
          </div>
        </div>
      </div>
    </section>
  );
}
