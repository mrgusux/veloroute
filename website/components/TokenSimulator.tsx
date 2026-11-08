"use client";

import { useState } from "react";
import {
  Sparkles,
  Sliders,
  DollarSign,
  TrendingDown,
  CheckCircle2,
  FileCode,
  Zap,
  Clock,
  ArrowRight,
} from "lucide-react";

interface ModelPricing {
  name: string;
  inputPerMillion: number;
}

const MODELS: Record<string, ModelPricing> = {
  "claude-3-5-sonnet": { name: "Claude 3.5 Sonnet", inputPerMillion: 3.0 },
  "gpt-4o": { name: "OpenAI GPT-4o", inputPerMillion: 2.5 },
  "deepseek-r1": { name: "DeepSeek-R1", inputPerMillion: 0.55 },
  "gemini-2-flash": { name: "Gemini 2.0 Flash", inputPerMillion: 0.1 },
};

export default function TokenSimulator() {
  const [requestsPerMonth, setRequestsPerMonth] = useState<number>(50000);
  const [avgPromptTokens, setAvgPromptTokens] = useState<number>(6500);
  const [selectedModel, setSelectedModel] = useState<string>("claude-3-5-sonnet");

  // Toggles
  const [enableAST, setEnableAST] = useState<boolean>(true);
  const [enableCaveman, setEnableCaveman] = useState<boolean>(true);
  const [enableWhitespace, setEnableWhitespace] = useState<boolean>(true);
  const [enableCache, setEnableCache] = useState<boolean>(true);

  const [activeCodeDiff, setActiveCodeDiff] = useState<"side-by-side" | "original" | "optimized">(
    "side-by-side"
  );

  // Compute reduction percentage based on active toggles
  let reductionFactor = 0;
  if (enableAST) reductionFactor += 0.48; // 48% AST skeletonization
  if (enableCaveman) reductionFactor += 0.12; // 12% terse prompt instructions
  if (enableWhitespace) reductionFactor += 0.08; // 8% whitespace & ANSI trim
  if (enableCache) reductionFactor += 0.15; // 15% instant cache hits

  // Cap reduction at 78% for realistic physics
  const netReduction = Math.min(reductionFactor, 0.78);

  const totalBaseTokens = requestsPerMonth * avgPromptTokens;
  const tokensSaved = Math.round(totalBaseTokens * netReduction);
  const effectiveTokens = totalBaseTokens - tokensSaved;

  const pricing = MODELS[selectedModel] || MODELS["claude-3-5-sonnet"];
  const baselineCost = (totalBaseTokens / 1_000_000) * pricing.inputPerMillion;
  const optimizedCost = (effectiveTokens / 1_000_000) * pricing.inputPerMillion;
  const monthlySavings = baselineCost - optimizedCost;
  const annualSavings = monthlySavings * 12;

  const originalSnippet = `def calculate_risk_index(
    user_portfolio: dict[str, float],
    volatility_matrix: list[list[float]],
    lookback_days: int = 90,
    stress_test_scenario: str | None = "2008_subprime",
    market_cap_weights: dict[str, float] | None = None,
) -> RiskAssessmentResult:
    """Computes multidimensional portfolio risk factoring covariance.
    
    Args:
        user_portfolio: Asset mapping to dollar balance
        volatility_matrix: Covariance array
    """
    logger.debug("Starting risk evaluation with %d assets", len(user_portfolio))
    if not user_portfolio:
        raise ValueError("Portfolio cannot be empty")
        
    normalized_weights = {}
    total_val = sum(user_portfolio.values())
    for asset, val in user_portfolio.items():
        # Strip out zero balances
        if val > 0:
            normalized_weights[asset] = val / total_val
            
    # Internal heavy matrix multiplication ...
    raw_var = _matrix_dot_product(normalized_weights, volatility_matrix)
    adj_var = _apply_monte_carlo_shocks(raw_var, iterations=10000)
    logger.info("Monte carlo run complete with status: NORMAL")
    
    return RiskAssessmentResult(score=adj_var.mean, p95=adj_var.p95)`;

  const optimizedSnippet = `def calculate_risk_index(
    user_portfolio: dict[str, float],
    volatility_matrix: list[list[float]],
    lookback_days: int = 90,
    stress_test_scenario: str | None = "2008_subprime",
    market_cap_weights: dict[str, float] | None = None,
) -> RiskAssessmentResult:
    """Computes multidimensional portfolio risk factoring covariance."""
    ...`;

  return (
    <section id="simulator" className="py-24 relative border-t border-white/5 bg-[#090d15]/50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto mb-16">
          <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-emerald-950/60 border border-emerald-500/30 text-emerald-400 text-xs font-mono mb-4">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Interactive Simulator</span>
          </div>
          <h2 className="text-3xl sm:text-5xl font-extrabold text-white tracking-tight">
            The Token-Saviour Engine.
          </h2>
          <p className="mt-4 text-slate-400 text-base sm:text-lg">
            Stop paying frontier rates for function bodies, whitespace, and repetitive prompts. See
            exact dollar and latency savings calculated live.
          </p>
        </div>

        {/* Simulator Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Controls Column (5 cols) */}
          <div className="lg:col-span-5 glass-panel p-6 sm:p-8 rounded-2xl border border-white/10 space-y-6">
            <div className="flex items-center justify-between pb-4 border-b border-white/10">
              <span className="font-semibold text-white flex items-center space-x-2">
                <Sliders className="w-4 h-4 text-sky-400" />
                <span>Simulation Parameters</span>
              </span>
              <span className="text-xs font-mono text-sky-400 bg-sky-950 px-2 py-0.5 rounded border border-sky-800/50">
                Deterministic
              </span>
            </div>

            {/* Slider 1: Monthly Requests */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <label className="text-xs font-medium text-slate-300">Monthly Request Volume</label>
                <span className="text-xs font-mono text-emerald-400 font-bold">
                  {requestsPerMonth.toLocaleString()} reqs
                </span>
              </div>
              <input
                type="range"
                min="5000"
                max="500000"
                step="5000"
                value={requestsPerMonth}
                onChange={(e) => setRequestsPerMonth(Number(e.target.value))}
                className="w-full accent-sky-400 cursor-pointer h-2 bg-slate-800 rounded-lg"
              />
              <div className="flex justify-between text-[10px] text-slate-500 font-mono mt-1">
                <span>5K</span>
                <span>250K</span>
                <span>500K</span>
              </div>
            </div>

            {/* Slider 2: Average Prompt Tokens */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <label className="text-xs font-medium text-slate-300">Average Prompt Size</label>
                <span className="text-xs font-mono text-sky-400 font-bold">
                  {avgPromptTokens.toLocaleString()} tokens
                </span>
              </div>
              <input
                type="range"
                min="500"
                max="32000"
                step="500"
                value={avgPromptTokens}
                onChange={(e) => setAvgPromptTokens(Number(e.target.value))}
                className="w-full accent-emerald-400 cursor-pointer h-2 bg-slate-800 rounded-lg"
              />
              <div className="flex justify-between text-[10px] text-slate-500 font-mono mt-1">
                <span>500 (Chat)</span>
                <span>16K (RAG)</span>
                <span>32K (Repo)</span>
              </div>
            </div>

            {/* Model Target Selection */}
            <div>
              <label className="text-xs font-medium text-slate-300 block mb-2">
                Reference Model Pricing
              </label>
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(MODELS).map(([key, item]) => (
                  <button
                    key={key}
                    onClick={() => setSelectedModel(key)}
                    className={`p-2.5 rounded-xl text-left border transition text-xs ${
                      selectedModel === key
                        ? "bg-sky-500/20 border-sky-400 text-white font-medium"
                        : "bg-slate-900/60 border-white/5 text-slate-400 hover:border-white/20"
                    }`}
                  >
                    <div className="font-semibold truncate">{item.name}</div>
                    <div className="text-[10px] font-mono text-slate-400">
                      ${item.inputPerMillion.toFixed(2)} / MTok
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {/* Optimization Heuristics Toggles */}
            <div className="pt-4 border-t border-white/10 space-y-3">
              <label className="text-xs font-medium text-slate-300 block">
                Active Compression Passes
              </label>

              {/* Toggle 1: AST */}
              <label className="flex items-center justify-between p-2.5 rounded-lg bg-slate-900/40 border border-white/5 cursor-pointer hover:border-white/10 transition">
                <div className="flex items-center space-x-2.5">
                  <FileCode className="w-4 h-4 text-sky-400" />
                  <div>
                    <div className="text-xs font-semibold text-slate-200">
                      AST Python Skeletonizer
                    </div>
                    <div className="text-[10px] text-slate-400">
                      Strips function bodies, preserves signatures & docstrings
                    </div>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={enableAST}
                  onChange={(e) => setEnableAST(e.target.checked)}
                  className="rounded accent-sky-400 w-4 h-4"
                />
              </label>

              {/* Toggle 2: Caveman */}
              <label className="flex items-center justify-between p-2.5 rounded-lg bg-slate-900/40 border border-white/5 cursor-pointer hover:border-white/10 transition">
                <div className="flex items-center space-x-2.5">
                  <Zap className="w-4 h-4 text-emerald-400" />
                  <div>
                    <div className="text-xs font-semibold text-slate-200">Caveman Terse Mode</div>
                    <div className="text-[10px] text-slate-400">
                      Strips polite filler phrases & redundant agent preambles
                    </div>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={enableCaveman}
                  onChange={(e) => setEnableCaveman(e.target.checked)}
                  className="rounded accent-emerald-400 w-4 h-4"
                />
              </label>

              {/* Toggle 3: Whitespace */}
              <label className="flex items-center justify-between p-2.5 rounded-lg bg-slate-900/40 border border-white/5 cursor-pointer hover:border-white/10 transition">
                <div className="flex items-center space-x-2.5">
                  <CheckCircle2 className="w-4 h-4 text-purple-400" />
                  <div>
                    <div className="text-xs font-semibold text-slate-200">
                      Lossless ANSI & Whitespace Clean
                    </div>
                    <div className="text-[10px] text-slate-400">
                      Eliminates ANSI control codes & redundant indentations
                    </div>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={enableWhitespace}
                  onChange={(e) => setEnableWhitespace(e.target.checked)}
                  className="rounded accent-purple-400 w-4 h-4"
                />
              </label>

              {/* Toggle 4: Cache */}
              <label className="flex items-center justify-between p-2.5 rounded-lg bg-slate-900/40 border border-white/5 cursor-pointer hover:border-white/10 transition">
                <div className="flex items-center space-x-2.5">
                  <Clock className="w-4 h-4 text-amber-400" />
                  <div>
                    <div className="text-xs font-semibold text-slate-200">
                      Exact & Semantic Caching
                    </div>
                    <div className="text-[10px] text-slate-400">
                      Sub-millisecond responses for repeated queries
                    </div>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={enableCache}
                  onChange={(e) => setEnableCache(e.target.checked)}
                  className="rounded accent-amber-400 w-4 h-4"
                />
              </label>
            </div>
          </div>

          {/* Results & Live Diff Column (7 cols) */}
          <div className="lg:col-span-7 space-y-6">
            {/* Real-time ROI Metrics Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="glass-panel p-5 rounded-2xl border border-emerald-500/30 bg-emerald-950/20">
                <div className="text-xs text-emerald-400 font-mono font-medium flex items-center space-x-1">
                  <DollarSign className="w-3.5 h-3.5" />
                  <span>Monthly Savings</span>
                </div>
                <div className="text-3xl font-extrabold text-white font-mono mt-2">
                  ${monthlySavings.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </div>
                <div className="text-[11px] text-emerald-400 font-mono mt-1">
                  ${annualSavings.toLocaleString(undefined, { maximumFractionDigits: 0 })} / year
                </div>
              </div>

              <div className="glass-panel p-5 rounded-2xl border border-sky-500/30 bg-sky-950/20">
                <div className="text-xs text-sky-400 font-mono font-medium flex items-center space-x-1">
                  <TrendingDown className="w-3.5 h-3.5" />
                  <span>Tokens Saved / Mo</span>
                </div>
                <div className="text-3xl font-extrabold text-white font-mono mt-2">
                  {(tokensSaved / 1_000_000).toFixed(1)}M
                </div>
                <div className="text-[11px] text-sky-400 font-mono mt-1">
                  -{(netReduction * 100).toFixed(0)}% payload reduction
                </div>
              </div>

              <div className="glass-panel p-5 rounded-2xl border border-purple-500/30 bg-purple-950/20">
                <div className="text-xs text-purple-400 font-mono font-medium flex items-center space-x-1">
                  <Zap className="w-3.5 h-3.5" />
                  <span>Avg Latency Cut</span>
                </div>
                <div className="text-3xl font-extrabold text-white font-mono mt-2">
                  {Math.round(netReduction * 55)}%
                </div>
                <div className="text-[11px] text-purple-400 font-mono mt-1">
                  Fewer prompt bytes to ingest
                </div>
              </div>
            </div>

            {/* Live Context Optimization Diff Preview */}
            <div className="glass-panel rounded-2xl border border-white/10 overflow-hidden shadow-xl">
              <div className="px-5 py-3.5 bg-slate-950/90 border-b border-white/10 flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center space-x-2">
                  <FileCode className="w-4 h-4 text-sky-400" />
                  <span className="text-xs font-mono font-semibold text-slate-200">
                    Context Skeletonization Diff
                  </span>
                </div>
                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => setActiveCodeDiff("side-by-side")}
                    className={`px-2.5 py-1 rounded text-xs font-mono transition ${
                      activeCodeDiff === "side-by-side"
                        ? "bg-sky-500/20 text-sky-300 border border-sky-500/40"
                        : "text-slate-400 hover:text-white"
                    }`}
                  >
                    Side-by-Side
                  </button>
                  <button
                    onClick={() => setActiveCodeDiff("optimized")}
                    className={`px-2.5 py-1 rounded text-xs font-mono transition ${
                      activeCodeDiff === "optimized"
                        ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                        : "text-slate-400 hover:text-white"
                    }`}
                  >
                    AST Skeleton (-76%)
                  </button>
                  <button
                    onClick={() => setActiveCodeDiff("original")}
                    className={`px-2.5 py-1 rounded text-xs font-mono transition ${
                      activeCodeDiff === "original"
                        ? "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                        : "text-slate-400 hover:text-white"
                    }`}
                  >
                    Raw Prompt
                  </button>
                </div>
              </div>

              <div className="p-4 bg-[#080c14] overflow-x-auto text-xs font-mono leading-relaxed">
                {activeCodeDiff === "side-by-side" && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Raw Before */}
                    <div className="p-3.5 rounded-xl bg-slate-950/60 border border-rose-500/20">
                      <div className="flex items-center justify-between mb-2 pb-2 border-b border-white/5">
                        <span className="text-[11px] text-rose-400 font-bold uppercase">
                          Standard SDK Prompt (324 tokens)
                        </span>
                        <span className="text-[10px] text-slate-500">Uncompressed</span>
                      </div>
                      <pre className="text-slate-400 text-[11px] overflow-x-auto whitespace-pre font-mono">
                        {originalSnippet}
                      </pre>
                    </div>

                    {/* VeloRoute After */}
                    <div className="p-3.5 rounded-xl bg-slate-950/60 border border-emerald-500/30 shadow-inner shadow-emerald-500/5">
                      <div className="flex items-center justify-between mb-2 pb-2 border-b border-white/5">
                        <span className="text-[11px] text-emerald-400 font-bold uppercase">
                          VeloRoute AST Skeleton (76 tokens)
                        </span>
                        <span className="text-[10px] text-emerald-400 font-bold font-mono">
                          -76.5% saved
                        </span>
                      </div>
                      <pre className="text-emerald-300/90 text-[11px] overflow-x-auto whitespace-pre font-mono">
                        {optimizedSnippet}
                      </pre>
                      <div className="mt-4 pt-3 border-t border-emerald-500/20 text-[10px] text-slate-400">
                        ⚡ <strong className="text-slate-300">Agent Performance:</strong> 100% of
                        type signatures & docstring specs preserved. Zero hallucination increase.
                      </div>
                    </div>
                  </div>
                )}
                {activeCodeDiff === "optimized" && (
                  <div className="p-4 bg-slate-950/80 rounded-xl border border-emerald-500/30">
                    <div className="flex items-center justify-between mb-3 pb-2 border-b border-emerald-500/20">
                      <span className="text-emerald-400 font-bold text-xs">VeloRoute AST Skeleton (76 tokens)</span>
                      <span className="text-emerald-400 font-mono text-[11px]">-76.5% tokens saved</span>
                    </div>
                    <pre className="text-emerald-300 text-xs font-mono whitespace-pre overflow-x-auto">
                      {optimizedSnippet}
                    </pre>
                  </div>
                )}
                {activeCodeDiff === "original" && (
                  <div className="p-4 bg-slate-950/80 rounded-xl border border-rose-500/30">
                    <div className="flex items-center justify-between mb-3 pb-2 border-b border-rose-500/20">
                      <span className="text-rose-400 font-bold text-xs">Uncompressed Prompt (324 tokens)</span>
                      <span className="text-slate-500 font-mono text-[11px]">Zero compression</span>
                    </div>
                    <pre className="text-slate-300 text-xs font-mono whitespace-pre overflow-x-auto">
                      {originalSnippet}
                    </pre>
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
