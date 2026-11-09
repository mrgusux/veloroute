"use client";

import { useState, useMemo } from "react";
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Check,
  Copy,
  Zap,
  Cpu,
  Layers,
  ArrowUpRight,
} from "lucide-react";

interface ModelItem {
  id: string;
  name: string;
  provider: "ANTHROPIC" | "OPENAI" | "DEEPSEEK" | "GOOGLE" | "ALIBABA" | "META" | "MISTRAL";
  badge?: "FEATURED" | "NEW" | "POPULAR" | "TOP CODING" | "OPEN SOURCE" | "FAST REASONING";
  description: string;
  category: "Reasoning" | "Coding" | "Multimodal" | "Open Weights" | "Fast Speed";
  context: string;
  latency: string;
  fallback: string;
  tags: string[];
  ditherHue: string;
}

const MODELS_DATA: ModelItem[] = [
  {
    id: "anthropic/claude-3-7-sonnet",
    name: "Claude 3.7 Sonnet",
    provider: "ANTHROPIC",
    badge: "FEATURED",
    description:
      "State-of-the-art hybrid reasoning model with dynamically controllable chain-of-thought and elite coding synthesis.",
    category: "Reasoning",
    context: "200k",
    latency: "420ms",
    fallback: "openai/gpt-4o",
    tags: ["Hybrid Thinking", "Code Synth", "Tool Calling"],
    ditherHue: "from-[#0055FF]/30 to-[#111114]",
  },
  {
    id: "openai/gpt-4.5-preview",
    name: "GPT-4.5 Preview",
    provider: "OPENAI",
    badge: "NEW",
    description:
      "Flagship frontier model with massive world knowledge, creative intuition, and deep context awareness.",
    category: "Reasoning",
    context: "128k",
    latency: "560ms",
    fallback: "anthropic/claude-3-5-sonnet",
    tags: ["Creative Depth", "World Knowledge", "RL Tuned"],
    ditherHue: "from-[#10b981]/25 to-[#111114]",
  },
  {
    id: "deepseek/deepseek-r1",
    name: "DeepSeek R1",
    provider: "DEEPSEEK",
    badge: "POPULAR",
    description:
      "Open-weights frontier reasoning model trained via large-scale reinforcement learning. Native speculative hedging target.",
    category: "Reasoning",
    context: "64k",
    latency: "380ms",
    fallback: "openai/o3-mini",
    tags: ["CoT Reasoning", "Open Weights", "Hedging"],
    ditherHue: "from-[#0055FF]/40 to-[#18181C]",
  },
  {
    id: "google/gemini-2.5-pro",
    name: "Gemini 2.5 Pro",
    provider: "GOOGLE",
    badge: "FEATURED",
    description:
      "Multimodal titan featuring 1M+ token native context window with VeloRoute KV-Cache prefix affinity.",
    category: "Multimodal",
    context: "1,000k",
    latency: "310ms",
    fallback: "anthropic/claude-3-7-sonnet",
    tags: ["1M Context", "Audio & Video", "KV-Affinity"],
    ditherHue: "from-[#3b82f6]/30 to-[#111114]",
  },
  {
    id: "alibaba/qwen-2.5-coder-32b",
    name: "Qwen 2.5 Coder 32B",
    provider: "ALIBABA",
    badge: "TOP CODING",
    description:
      "Ultra-competitive coding powerhouse optimized for code repair, AST skeletonizer context compression, and local Ollama.",
    category: "Coding",
    context: "128k",
    latency: "180ms",
    fallback: "deepseek/deepseek-coder",
    tags: ["Fast Latency", "Ollama Native", "AST Compressed"],
    ditherHue: "from-[#f59e0b]/25 to-[#111114]",
  },
  {
    id: "meta/llama-3.3-70b-instruct",
    name: "Llama 3.3 70B Instruct",
    provider: "META",
    badge: "OPEN SOURCE",
    description:
      "High-throughput open foundational model benchmarked against proprietary flagships with sub-millisecond gateway proxying.",
    category: "Open Weights",
    context: "128k",
    latency: "110ms",
    fallback: "mistral/mistral-large",
    tags: ["Groq Accelerated", "Low Cost", "Smart Routing"],
    ditherHue: "from-[#0055FF]/30 to-[#111114]",
  },
  {
    id: "mistral/mistral-large-2411",
    name: "Mistral Large 2411",
    provider: "MISTRAL",
    badge: "FEATURED",
    description:
      "Top-tier European multilingual model with strict system prompt guardrails and precise JSON structured output.",
    category: "Reasoning",
    context: "128k",
    latency: "290ms",
    fallback: "openai/gpt-4o-mini",
    tags: ["JSON Strict", "Multilingual", "EU Hosted"],
    ditherHue: "from-[#ef4444]/25 to-[#111114]",
  },
  {
    id: "openai/o3-mini",
    name: "OpenAI o3-mini",
    provider: "OPENAI",
    badge: "FAST REASONING",
    description:
      "Cost-efficient STEM reasoning model with flexible reasoning effort modes and sub-second first-token response.",
    category: "Fast Speed",
    context: "128k",
    latency: "240ms",
    fallback: "deepseek/deepseek-r1",
    tags: ["STEM Reasoning", "High RPS", "Direct Wire"],
    ditherHue: "from-[#10b981]/30 to-[#111114]",
  },
];

const PROVIDERS = ["ALL", "ANTHROPIC", "OPENAI", "DEEPSEEK", "GOOGLE", "ALIBABA", "META", "MISTRAL"] as const;
const CATEGORIES = ["All Categories", "Reasoning", "Coding", "Multimodal", "Open Weights", "Fast Speed"] as const;

export default function ModelDirectory({ externalFilter = "" }: { externalFilter?: string }) {
  const [selectedProvider, setSelectedProvider] = useState<string>("ALL");
  const [selectedCategory, setSelectedCategory] = useState<string>("All Categories");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState<number>(0);
  const pageSize = 4;

  const filteredModels = useMemo(() => {
    return MODELS_DATA.filter((m) => {
      const matchSearch =
        externalFilter === "" ||
        m.name.toLowerCase().includes(externalFilter.toLowerCase()) ||
        m.id.toLowerCase().includes(externalFilter.toLowerCase()) ||
        m.tags.some((t) => t.toLowerCase().includes(externalFilter.toLowerCase())) ||
        m.provider.toLowerCase().includes(externalFilter.toLowerCase());

      const matchProvider = selectedProvider === "ALL" || m.provider === selectedProvider;
      const matchCategory = selectedCategory === "All Categories" || m.category === selectedCategory;

      return matchSearch && matchProvider && matchCategory;
    });
  }, [externalFilter, selectedProvider, selectedCategory]);

  const totalPages = Math.ceil(filteredModels.length / pageSize) || 1;
  const currentSlice = filteredModels.slice(currentPage * pageSize, (currentPage + 1) * pageSize);

  const handleCopy = (id: string) => {
    navigator.clipboard.writeText(id);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <section id="models" className="py-20 relative bg-[#000000] border-t border-[#18181C]">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-8 lg:px-[120px]">
        {/* Section Header with Category Label, Title & Pagination per DESIGN.md */}
        <div className="flex flex-col md:flex-row md:items-end justify-between mb-8 gap-4">
          <div>
            <div className="inline-flex items-center space-x-2 px-2.5 py-1 rounded-none bg-[#18181C] text-[#FBFBFF] text-[11px] font-bold tracking-[0.1em] uppercase mb-3">
              <span>FEATURED</span>
            </div>
            <h2 className="text-3xl sm:text-4xl lg:text-[2.625rem] font-semibold text-[#FBFBFF] tracking-[-0.025em] leading-[0.9]">
              Popular Models &amp; Providers
            </h2>
            <p className="mt-3 text-sm text-[#A7A9B8] max-w-2xl font-normal leading-relaxed">
              Dynamically route requests across 80+ foundation models with sub-millisecond failover,
              speculative hedging, and automatic cost/latency optimization.
            </p>
          </div>

          {/* Pagination Controls */}
          <div className="flex items-center space-x-2 shrink-0">
            <span className="text-xs font-mono text-[#5B5D6B] mr-2">
              Page {currentPage + 1} / {totalPages}
            </span>
            <button
              onClick={() => setCurrentPage((p) => Math.max(0, p - 1))}
              disabled={currentPage === 0}
              className="w-9 h-9 rounded-none bg-[#0B0B0D] border border-[#18181C] flex items-center justify-center text-[#DFE0EA] hover:border-white/30 disabled:opacity-40 disabled:hover:border-[#18181C] transition"
              aria-label="Previous page"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => setCurrentPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={currentPage >= totalPages - 1}
              className="w-9 h-9 rounded-none bg-[#0B0B0D] border border-[#18181C] flex items-center justify-center text-[#DFE0EA] hover:border-white/30 disabled:opacity-40 disabled:hover:border-[#18181C] transition"
              aria-label="Next page"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Filter Pills */}
        <div className="flex flex-wrap items-center gap-2 mb-8">
          <div className="flex flex-wrap items-center gap-1.5 mr-4">
            {PROVIDERS.map((prov) => (
              <button
                key={prov}
                onClick={() => {
                  setSelectedProvider(prov);
                  setCurrentPage(0);
                }}
                className={`px-3 py-1.5 text-xs font-mono rounded-none uppercase tracking-wider transition ${
                  selectedProvider === prov
                    ? "bg-[#0055FF] text-[#FBFBFF] font-semibold"
                    : "bg-[#0B0B0D] text-[#A7A9B8] hover:text-[#FBFBFF] border border-[#18181C]"
                }`}
              >
                {prov}
              </button>
            ))}
          </div>

          <div className="hidden sm:flex items-center space-x-1.5 border-l border-[#18181C] pl-4">
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                onClick={() => {
                  setSelectedCategory(cat);
                  setCurrentPage(0);
                }}
                className={`px-2.5 py-1 text-[11px] rounded-none transition ${
                  selectedCategory === cat
                    ? "bg-[#18181C] text-[#FBFBFF] font-medium"
                    : "text-[#5B5D6B] hover:text-[#DFE0EA]"
                }`}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>

        {/* Model Grid per DESIGN.md: 1.25rem gap, 0 border-radius */}
        {currentSlice.length === 0 ? (
          <div className="bg-[#0B0B0D] p-12 text-center border border-[#18181C]">
            <p className="text-sm text-[#A7A9B8]">No models match your current filters.</p>
            <button
              onClick={() => {
                setSelectedProvider("ALL");
                setSelectedCategory("All Categories");
              }}
              className="mt-4 px-4 py-2 bg-[#0055FF] text-[#FBFBFF] text-xs font-semibold uppercase tracking-wider"
            >
              Reset Filters
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
            {currentSlice.map((model) => (
              <div
                key={model.id}
                className="bg-[#0B0B0D] border border-transparent hover:border-[#25252C] transition-all flex flex-col justify-between rounded-none overflow-hidden group"
              >
                <div>
                  {/* Dithered Posterized Thumbnail Area */}
                  <div className={`relative h-36 bg-gradient-to-br ${model.ditherHue} p-4 flex flex-col justify-between border-b border-[#18181C]`}>
                    {/* Dither grid overlay */}
                    <div className="absolute inset-0 bg-[radial-gradient(#ffffff_1px,transparent_1px)] [background-size:12px_12px] opacity-15 pointer-events-none" />
                    
                    <div className="flex items-center justify-between relative z-10">
                      <span className="text-[10px] font-bold font-mono tracking-[0.1em] text-[#A7A9B8] bg-[#000000]/80 px-2 py-0.5 uppercase border border-[#18181C]">
                        {model.provider}
                      </span>
                      {model.badge && (
                        <span className="text-[9px] font-bold font-mono tracking-widest text-[#FBFBFF] bg-[#0055FF] px-2 py-0.5 uppercase">
                          {model.badge}
                        </span>
                      )}
                    </div>

                    <div className="relative z-10 flex items-center justify-between">
                      <div className="flex items-center space-x-2 text-xs font-mono text-[#FBFBFF]">
                        <Zap className="w-3.5 h-3.5 text-[#0055FF]" />
                        <span>{model.latency}</span>
                      </div>
                      <span className="text-[11px] font-mono text-[#DFE0EA] bg-[#000000]/60 px-1.5 py-0.5">
                        {model.context} ctx
                      </span>
                    </div>
                  </div>

                  {/* Card Content with 1.25rem internal padding */}
                  <div className="p-5">
                    <div className="flex items-start justify-between mb-1.5">
                      <h3 className="text-base font-semibold text-[#FBFBFF] group-hover:text-[#0055FF] transition-colors tracking-tight">
                        {model.name}
                      </h3>
                      <button
                        onClick={() => handleCopy(model.id)}
                        className="text-[#5B5D6B] hover:text-[#FBFBFF] transition p-1"
                        title="Copy model ID"
                      >
                        {copiedId === model.id ? (
                          <Check className="w-3.5 h-3.5 text-[#10b981]" />
                        ) : (
                          <Copy className="w-3.5 h-3.5" />
                        )}
                      </button>
                    </div>

                    <p className="text-xs text-[#A7A9B8] line-clamp-3 leading-relaxed mb-4">
                      {model.description}
                    </p>

                    {/* Capability Tags */}
                    <div className="flex flex-wrap gap-1.5 mb-4">
                      {model.tags.map((tag) => (
                        <span
                          key={tag}
                          className="text-[10px] font-bold tracking-[0.05em] uppercase text-[#DFE0EA] bg-[#18181C] px-2 py-0.5 rounded-none"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>

                    {/* Fallback & Routing Target */}
                    <div className="text-[11px] font-mono text-[#5B5D6B] pt-3 border-t border-[#18181C] flex items-center justify-between">
                      <span>Fallback:</span>
                      <span className="text-[#A7A9B8] truncate max-w-[150px]">{model.fallback}</span>
                    </div>
                  </div>
                </div>

                {/* Card Action Button */}
                <div className="p-5 pt-0">
                  <a
                    href="#quickstart"
                    className="w-full py-2 bg-[#111114] hover:bg-[#0055FF] text-[#DFE0EA] hover:text-[#FBFBFF] text-xs font-mono uppercase tracking-wider flex items-center justify-center space-x-1.5 transition border border-[#18181C] hover:border-transparent"
                  >
                    <span>Route Model</span>
                    <ArrowUpRight className="w-3.5 h-3.5" />
                  </a>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
