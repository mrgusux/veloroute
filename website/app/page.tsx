import CyberBackground from "@/components/CyberBackground";
import Navbar from "@/components/Navbar";
import Hero from "@/components/Hero";
import TokenSimulator from "@/components/TokenSimulator";
import ArchitectureTabs from "@/components/ArchitectureTabs";
import CodeSwitcher from "@/components/CodeSwitcher";
import BenchmarkMatrix from "@/components/BenchmarkMatrix";
import DeploySection from "@/components/DeploySection";
import Footer from "@/components/Footer";
import {
  Zap,
  Shield,
  Layers,
  Cpu,
  RefreshCw,
  Lock,
  GitCompare,
  Terminal,
  Activity,
  CheckCircle,
} from "lucide-react";

export default function Home() {
  const features = [
    {
      icon: Zap,
      title: "Sub-Millisecond Wire Proxy",
      description:
        "Deterministic routing layer adds less than 0.8ms latency. Pure async Python 3.12+ with zero heavy ML inference overhead.",
      tag: "< 0.8ms Overhead",
    },
    {
      icon: Layers,
      title: "AST Context Skeletonizer",
      description:
        "Strips implementation bodies from Python files, preserving typed function signatures and docstrings. Saves up to 75% context tokens.",
      tag: "Token Saviour",
    },
    {
      icon: RefreshCw,
      title: "Mid-Stream Seamless Failover",
      description:
        "If a provider halts mid-stream, VeloRoute reconnects to a healthy fallback provider and resumes without breaking client SSE connections.",
      tag: "Zero-Downtime",
    },
    {
      icon: Shield,
      title: "Sentinel Circuit Breakers",
      description:
        "3-state deterministic health machine (Closed, Open, Half-Open). Automatic exponential backoff with full jitter prevents cascading failures.",
      tag: "Auto-Healing",
    },
    {
      icon: Lock,
      title: "Shannon Entropy Secret Shield",
      description:
        "Scans for high-entropy secrets and PII in real-time, redacting them before cloud transmission and unmasking them losslessly in responses.",
      tag: "Zero-Retention",
    },
    {
      icon: Cpu,
      title: "Universal MCP SSE Bridge",
      description:
        "Connects stdio and SSE Model Context Protocol tool servers directly to LLMs with automatic RTK token compression.",
      tag: "MCP Native",
    },
  ];

  return (
    <div className="relative min-h-screen bg-[#07090e] text-slate-100 flex flex-col selection:bg-sky-500/30 selection:text-sky-300">
      <CyberBackground />
      <Navbar />

      <main className="flex-1 z-10">
        <Hero />

        {/* Feature Grid Section */}
        <section id="features" className="py-20 relative border-t border-white/5 bg-[#090d16]/30">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="text-center max-w-3xl mx-auto mb-16">
              <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-sky-950/60 border border-sky-500/30 text-sky-400 text-xs font-mono mb-4">
                <Activity className="w-3.5 h-3.5" />
                <span>Core Capabilities</span>
              </div>
              <h2 className="text-3xl sm:text-5xl font-extrabold text-white tracking-tight">
                Built for High-Throughput Production.
              </h2>
              <p className="mt-4 text-slate-400 text-base sm:text-lg">
                Engineered from the ground up for extreme concurrency, deterministic cost reduction,
                and mission-critical resilience.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {features.map((feat, idx) => {
                const Icon = feat.icon;
                return (
                  <div
                    key={idx}
                    className="glass-panel p-6 rounded-2xl border border-white/10 glass-panel-hover group flex flex-col justify-between"
                  >
                    <div>
                      <div className="flex items-center justify-between mb-4">
                        <div className="w-10 h-10 rounded-xl bg-slate-900 border border-sky-500/30 flex items-center justify-center group-hover:border-sky-400 transition">
                          <Icon className="w-5 h-5 text-sky-400 group-hover:scale-110 transition-transform" />
                        </div>
                        <span className="text-[10px] font-mono text-slate-400 bg-slate-900 px-2.5 py-1 rounded-md border border-white/5">
                          {feat.tag}
                        </span>
                      </div>
                      <h3 className="text-lg font-bold text-white mb-2 group-hover:text-sky-300 transition-colors">
                        {feat.title}
                      </h3>
                      <p className="text-sm text-slate-400 leading-relaxed">{feat.description}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        <TokenSimulator />
        <ArchitectureTabs />
        <CodeSwitcher />
        <BenchmarkMatrix />
        <DeploySection />
      </main>

      <Footer />
    </div>
  );
}
