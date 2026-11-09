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
    <div className="relative min-h-screen bg-[#000000] text-[#DFE0EA] flex flex-col selection:bg-[#0055FF]/40 selection:text-[#FBFBFF]">
      <CyberBackground />
      <Navbar />

      <main className="flex-1 z-10">
        <Hero />

        {/* Feature Grid Section */}
        <section id="features" className="py-20 relative border-t border-[#18181C] bg-[#000000]">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="text-center max-w-3xl mx-auto mb-16">
              <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-none bg-[#111114] border border-[#18181C] text-[#FBFBFF] text-[11px] font-mono uppercase tracking-widest mb-4">
                <Activity className="w-3.5 h-3.5 text-[#0055FF]" />
                <span>CORE CAPABILITIES</span>
              </div>
              <h2 className="text-3xl sm:text-5xl font-bold text-[#FBFBFF] tracking-tight">
                Engineered for High-Throughput Production.
              </h2>
              <p className="mt-4 text-[#A7A9B8] text-base sm:text-lg">
                Deterministic sub-millisecond routing, zero prompt retention, and mission-critical resilience.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {features.map((feat, idx) => {
                const Icon = feat.icon;
                return (
                  <div
                    key={idx}
                    className="bg-[#0B0B0D] p-6 rounded-none border border-[#18181C] hover:border-white/20 transition-all flex flex-col justify-between"
                  >
                    <div>
                      <div className="flex items-center justify-between mb-4">
                        <div className="w-9 h-9 rounded-none bg-[#111114] border border-[#18181C] flex items-center justify-center">
                          <Icon className="w-4 h-4 text-[#0055FF]" />
                        </div>
                        <span className="text-[10px] font-mono font-bold tracking-wider text-[#A7A9B8] bg-[#18181C] px-2.5 py-1 rounded-none uppercase">
                          {feat.tag}
                        </span>
                      </div>
                      <h3 className="text-base font-semibold text-[#FBFBFF] mb-2 tracking-tight">
                        {feat.title}
                      </h3>
                      <p className="text-xs sm:text-sm text-[#A7A9B8] leading-relaxed">{feat.description}</p>
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
