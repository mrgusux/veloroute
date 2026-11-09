import { ArrowRight } from "lucide-react";
import DockerCopyPill from "./hero/DockerCopyPill";
import StarCounter from "./hero/StarCounter";
import TerminalSimulator from "./hero/TerminalSimulator";

export default function Hero() {
  return (
    <section className="relative pt-28 pb-20 md:pt-36 md:pb-28 overflow-hidden bg-[#000000]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        {/* Top Feature Tag */}
        <div className="flex justify-center mb-6">
          <div className="inline-flex items-center space-x-2 px-3.5 py-1.5 rounded-none bg-[#0B0B0D] border border-[#18181C] text-xs text-[#DFE0EA]">
            <span className="w-1.5 h-1.5 rounded-none bg-[#0055FF]" />
            <span className="font-mono text-[#FBFBFF] font-semibold uppercase tracking-wider">VELOROUTE 1.0</span>
            <span className="text-[#5B5D6B]">•</span>
            <span className="text-[#A7A9B8]">SUB-MILLISECOND AI ROUTER &amp; TOKEN SAVIOUR</span>
            <ArrowRight className="w-3 h-3 text-[#5B5D6B]" />
          </div>
        </div>

        {/* Main Headline */}
        <div className="text-center max-w-4xl mx-auto mb-8">
          <h1 className="text-4xl sm:text-6xl lg:text-7xl font-bold tracking-tight text-[#FBFBFF] leading-[1.05]">
            Ultra-Fast Universal AI Gateway.{" "}
            <span className="text-[#0055FF]">
              Zero Retention.
            </span>{" "}
            Native Token Savings.
          </h1>
          <p className="mt-6 text-base sm:text-lg text-[#DFE0EA] max-w-2xl mx-auto font-normal leading-relaxed">
            Eliminate LLM outages with automated sentinel circuit breakers, speculative hedging,
            and AST context compression. Route across OpenAI, Anthropic, Gemini, Groq,
            and local Ollama with <span className="text-[#FBFBFF] font-semibold font-mono border-b border-[#0055FF] pb-0.5">&lt; 0.8ms</span> overhead.
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
          <div className="bg-[#0B0B0D] p-5 rounded-none border border-[#18181C] text-center">
            <div className="text-2xl sm:text-3xl font-bold text-[#0055FF] font-mono">&lt; 0.8ms</div>
            <div className="text-xs uppercase tracking-wider text-[#A7A9B8] mt-1 font-mono">Routing Overhead</div>
          </div>
          <div className="bg-[#0B0B0D] p-5 rounded-none border border-[#18181C] text-center">
            <div className="text-2xl sm:text-3xl font-bold text-[#FBFBFF] font-mono">Up to 75%</div>
            <div className="text-xs uppercase tracking-wider text-[#A7A9B8] mt-1 font-mono">Token Reduction</div>
          </div>
          <div className="bg-[#0B0B0D] p-5 rounded-none border border-[#18181C] text-center">
            <div className="text-2xl sm:text-3xl font-bold text-[#0055FF] font-mono">0 Outages</div>
            <div className="text-xs uppercase tracking-wider text-[#A7A9B8] mt-1 font-mono">Auto-Failover</div>
          </div>
          <div className="bg-[#0B0B0D] p-5 rounded-none border border-[#18181C] text-center">
            <div className="text-2xl sm:text-3xl font-bold text-[#FBFBFF] font-mono">224+ / 224+</div>
            <div className="text-xs uppercase tracking-wider text-[#A7A9B8] mt-1 font-mono">Unit Tests Passing</div>
          </div>
        </div>
      </div>
    </section>
  );
}
