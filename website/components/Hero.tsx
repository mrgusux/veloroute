import { ArrowRight } from "lucide-react";
import DockerCopyPill from "./hero/DockerCopyPill";
import StarCounter from "./hero/StarCounter";
import TerminalSimulator from "./hero/TerminalSimulator";

export default function Hero() {
  return (
    <section className="relative pt-32 pb-20 md:pt-40 md:pb-32 overflow-hidden">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        {/* Top Feature Pill */}
        <div className="flex justify-center mb-6">
          <div className="inline-flex items-center space-x-2 px-3.5 py-1.5 rounded-full bg-slate-900/90 border border-sky-500/30 text-xs text-slate-300 backdrop-blur-md shadow-inner shadow-sky-500/10 hover:border-sky-500/60 transition">
            <span className="flex h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="font-mono text-sky-400 font-semibold">VeloRoute v1.0</span>
            <span className="text-slate-500">•</span>
            <span>Sub-Millisecond Multi-Provider AI Gateway &amp; Token Saviour</span>
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
            &amp; Native Token Savings.
          </h1>
          <p className="mt-6 text-lg sm:text-xl text-slate-300 max-w-2xl mx-auto font-normal leading-relaxed">
            Eliminate LLM outages with automated sentinel circuit breakers, speculative hedging,
            and AST context compression. Route effortlessly between OpenAI, Anthropic, Gemini, Groq,
            and local Ollama with <span className="text-sky-300 font-semibold font-mono">&lt; 0.8ms</span> overhead.
          </p>
        </div>

        {/* Action Buttons & 1-Command Docker Run */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-14">
          <DockerCopyPill />
          <StarCounter />
        </div>

        {/* Live Interactive Terminal Preview */}
        <TerminalSimulator />

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
            <div className="text-2xl sm:text-3xl font-extrabold text-purple-400 font-mono">224+ / 224+</div>
            <div className="text-xs sm:text-sm text-slate-400 mt-1">Unit Tests Passing</div>
          </div>
        </div>
      </div>
    </section>
  );
}
