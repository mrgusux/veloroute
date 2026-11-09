"use client";

import { useState, useEffect } from "react";
import { ArrowRight, Terminal as TerminalIcon, Sparkles } from "lucide-react";
import DockerCopyPill from "./hero/DockerCopyPill";
import StarCounter from "./hero/StarCounter";
import TerminalSimulator from "./hero/TerminalSimulator";

interface Slide {
  id: string;
  number: string;
  label: string;
  headlinePrefix: string;
  headlineAccent: string;
  headlineSuffix: string;
  description: string;
  primaryCta: { label: string; href: string };
  secondaryCta: { label: string; href: string };
}

const SLIDES: Slide[] = [
  {
    id: "routing",
    number: "01",
    label: "DYNAMIC ROUTING",
    headlinePrefix: "Ultra-Fast Universal AI Gateway. ",
    headlineAccent: "Zero Retention.",
    headlineSuffix: " Native Token Savings.",
    description:
      "Eliminate LLM outages with automated sentinel circuit breakers, speculative hedging, and AST context compression. Route across OpenAI, Anthropic, Gemini, Groq, and local Ollama with < 0.8ms overhead.",
    primaryCta: { label: "Launch Console", href: "#quickstart" },
    secondaryCta: { label: "Explore 80+ Models", href: "#models" },
  },
  {
    id: "skeletonizer",
    number: "02",
    label: "AST TOKEN SKELETONIZER",
    headlinePrefix: "Save Up to 75% Context Tokens. ",
    headlineAccent: "Zero Loss.",
    headlineSuffix: " Python AST Precision.",
    description:
      "Strips function implementation bodies while retaining typed function signatures and docstrings. Feed massive multi-file codebases to coding agents without blowing context limits.",
    primaryCta: { label: "Try Token Simulator", href: "#simulator" },
    secondaryCta: { label: "Inspect Benchmarks", href: "#benchmarks" },
  },
  {
    id: "resilience",
    number: "03",
    label: "RESILIENCE & HEDGING",
    headlinePrefix: "Zero-Downtime Mid-Stream Failover. ",
    headlineAccent: "Deterministic.",
    headlineSuffix: " Speculative Hedging.",
    description:
      "3-state deterministic health machine (Closed, Open, Half-Open). Automatic exponential backoff with full jitter recovery prevents cascading failures and eliminates silent agent timeouts.",
    primaryCta: { label: "View Architecture", href: "#architecture" },
    secondaryCta: { label: "Deploy Gateway", href: "#quickstart" },
  },
];

export default function Hero() {
  const [activeSlide, setActiveSlide] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setActiveSlide((prev) => (prev + 1) % SLIDES.length);
    }, 9000);
    return () => clearInterval(timer);
  }, []);

  const slide = SLIDES[activeSlide];

  return (
    <section className="relative pt-24 pb-16 md:pt-32 md:pb-20 overflow-hidden bg-[#000000]">
      {/* Full-bleed background with atmospheric gradient overlay per DESIGN.md */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_80%_80%_at_50%_-20%,rgba(0,85,255,0.12),rgba(255,255,255,0))] pointer-events-none" />
      <div className="absolute inset-0 bg-grid-pattern opacity-40 pointer-events-none" />
      <div className="absolute inset-0 hero-overlay pointer-events-none" />

      <div className="max-w-[1440px] mx-auto px-4 sm:px-8 lg:px-[120px] relative z-10">
        {/* Top Feature Pill */}
        <div className="flex justify-start mb-6">
          <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-none bg-[#0B0B0D] border border-[#18181C] text-xs text-[#DFE0EA]">
            <span className="w-1.5 h-1.5 rounded-none bg-[#0055FF]" />
            <span className="font-mono text-[#FBFBFF] font-semibold uppercase tracking-wider text-[11px]">
              VELOROUTE 1.0
            </span>
            <span className="text-[#5B5D6B]">•</span>
            <span className="text-[#A7A9B8] text-[11px] font-mono">SUB-MILLISECOND AI ROUTER &amp; TOKEN SAVIOUR</span>
            <ArrowRight className="w-3 h-3 text-[#5B5D6B]" />
          </div>
        </div>

        {/* Hero Carousel Main Row */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 items-center mb-10">
          {/* Left Column: Display Typography (Stack Sans Notch style) */}
          <div className="lg:col-span-6 space-y-6">
            <h1 className="text-3xl sm:text-5xl lg:text-[3.75rem] font-semibold text-[#FBFBFF] tracking-[-0.025em] leading-[1.05] transition-all duration-300">
              {slide.headlinePrefix}
              <span className="text-[#0055FF]">{slide.headlineAccent}</span>
              {slide.headlineSuffix}
            </h1>

            <p className="text-[1.09375rem] leading-[1.625] text-[#DFE0EA] font-normal transition-all duration-300">
              {slide.description}
            </p>

            {/* Action Buttons: Primary #0055FF, Secondary Ghost #FFFFFF border */}
            <div className="flex flex-wrap items-center gap-3 pt-2">
              <a
                href={slide.primaryCta.href}
                className="h-11 px-6 bg-[#0055FF] hover:bg-[#0047D4] active:bg-[#003CB8] text-[#FBFBFF] text-sm font-medium flex items-center space-x-2 transition rounded-none"
              >
                <span>{slide.primaryCta.label}</span>
                <ArrowRight className="w-4 h-4" />
              </a>

              <a
                href={slide.secondaryCta.href}
                className="h-11 px-6 bg-transparent hover:bg-white hover:text-black text-[#FBFBFF] border border-[#FFFFFF] text-sm font-medium flex items-center space-x-2 transition rounded-none"
              >
                <span>{slide.secondaryCta.label}</span>
              </a>
            </div>

            {/* Quick 1-Command Pill */}
            <div className="pt-2 flex flex-col sm:flex-row items-start sm:items-center gap-3">
              <DockerCopyPill />
              <StarCounter />
            </div>
          </div>

          {/* Right Column: Terminal Simulator */}
          <div className="lg:col-span-6">
            <TerminalSimulator />
          </div>
        </div>

        {/* Tabbed Navigation Strip at Bottom of Hero per DESIGN.md */}
        <div className="border-t border-[#18181C] pt-4 mb-12">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {SLIDES.map((s, idx) => {
              const isActive = activeSlide === idx;
              return (
                <button
                  key={s.id}
                  onClick={() => setActiveSlide(idx)}
                  className={`text-left p-3.5 border transition-all rounded-none ${
                    isActive
                      ? "border-[#0055FF] bg-[#111114] text-[#FBFBFF]"
                      : "border-[#18181C] bg-[#0B0B0D] hover:border-[#25252C] text-[#5B5D6B]"
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className={`font-mono text-xs font-bold ${isActive ? "text-[#0055FF]" : "text-[#5B5D6B]"}`}>
                      {s.number}
                    </span>
                    {isActive && (
                      <span className="w-1.5 h-1.5 bg-[#0055FF] rounded-none animate-pulse" />
                    )}
                  </div>
                  <div className={`text-xs font-mono font-bold tracking-wider uppercase ${isActive ? "text-[#FBFBFF]" : "text-[#A7A9B8]"}`}>
                    {s.label}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Enterprise Metrics Ribbon per DESIGN.md */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-[#0B0B0D] p-5 rounded-none border border-[#18181C] text-center">
            <div className="text-2xl sm:text-3xl font-bold text-[#0055FF] font-mono">&lt; 0.8ms</div>
            <div className="text-[11px] uppercase tracking-wider text-[#A7A9B8] mt-1 font-mono">Routing Overhead</div>
          </div>
          <div className="bg-[#0B0B0D] p-5 rounded-none border border-[#18181C] text-center">
            <div className="text-2xl sm:text-3xl font-bold text-[#FBFBFF] font-mono">Up to 75%</div>
            <div className="text-[11px] uppercase tracking-wider text-[#A7A9B8] mt-1 font-mono">Token Reduction</div>
          </div>
          <div className="bg-[#0B0B0D] p-5 rounded-none border border-[#18181C] text-center">
            <div className="text-2xl sm:text-3xl font-bold text-[#0055FF] font-mono">0 Outages</div>
            <div className="text-[11px] uppercase tracking-wider text-[#A7A9B8] mt-1 font-mono">Auto-Failover</div>
          </div>
          <div className="bg-[#0B0B0D] p-5 rounded-none border border-[#18181C] text-center">
            <div className="text-2xl sm:text-3xl font-bold text-[#FBFBFF] font-mono">225 / 225</div>
            <div className="text-[11px] uppercase tracking-wider text-[#A7A9B8] mt-1 font-mono">Unit Tests Passing</div>
          </div>
        </div>
      </div>
    </section>
  );
}
