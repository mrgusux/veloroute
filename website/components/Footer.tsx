import { Zap, Github, MessageSquare, LifeBuoy, ArrowUpRight } from "lucide-react";

export default function Footer() {
  return (
    <footer className="border-t border-[#18181C] bg-[#0B0B0D] text-[#A7A9B8]">
      {/* Container with 40px 30px desktop padding per DESIGN.md */}
      <div className="max-w-[1440px] mx-auto px-6 md:px-8 py-10">
        {/* 5-Column Grid on Desktop: Brand Column Wide + 4 Link Columns */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-8 mb-10">
          {/* Brand Column (spans 2 columns on lg) */}
          <div className="lg:col-span-2 space-y-4">
            <div className="flex items-center space-x-2.5">
              <div className="w-7 h-7 rounded-none bg-[#0055FF] flex items-center justify-center">
                <Zap className="w-4 h-4 text-[#FBFBFF]" />
              </div>
              <span className="text-base font-bold text-[#FBFBFF] tracking-tight">
                VELO<span className="text-[#0055FF]">ROUTE</span>
              </span>
            </div>
            <p className="text-[#5B5D6B] text-xs max-w-sm leading-relaxed">
              Enterprise Universal AI Gateway, High-Availability LLM Routing &amp; Token-Saviour
              Optimization Engine. Zero heavy ML runtime, zero prompt retention, 100% open-source.
            </p>
            {/* Outline Buttons per DESIGN.md: Join Discord & Client Support */}
            <div className="flex flex-wrap items-center gap-2.5 pt-2">
              <a
                href="https://discord.gg/veloroute"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center space-x-1.5 px-3.5 py-2 rounded-none text-xs font-mono uppercase tracking-wider text-[#FBFBFF] border border-[#FFFFFF] hover:bg-white hover:text-black transition bg-transparent"
              >
                <MessageSquare className="w-3.5 h-3.5" />
                <span>Join Discord</span>
              </a>
              <a
                href="mailto:support@veloroute.dev"
                className="inline-flex items-center space-x-1.5 px-3.5 py-2 rounded-none text-xs font-mono uppercase tracking-wider text-[#FBFBFF] border border-[#FFFFFF] hover:bg-white hover:text-black transition bg-transparent"
              >
                <LifeBuoy className="w-3.5 h-3.5" />
                <span>Client Support</span>
              </a>
            </div>
          </div>

          {/* Link Column 1: Routing Engines */}
          <div>
            <h4 className="text-[#FBFBFF] font-bold mb-3.5 uppercase tracking-[1.1px] text-[11px]">
              ROUTING ENGINES
            </h4>
            <ul className="space-y-2 text-xs">
              <li>
                <a href="#architecture" className="text-[#A7A9B8] hover:text-[#FBFBFF] transition">
                  KV-Cache Affinity
                </a>
              </li>
              <li>
                <a href="#architecture" className="text-[#A7A9B8] hover:text-[#FBFBFF] transition">
                  Circuit Breakers
                </a>
              </li>
              <li>
                <a href="#architecture" className="text-[#A7A9B8] hover:text-[#FBFBFF] transition">
                  Speculative Hedging
                </a>
              </li>
              <li>
                <a href="#architecture" className="text-[#A7A9B8] hover:text-[#FBFBFF] transition">
                  Complexity Router
                </a>
              </li>
              <li>
                <a href="#models" className="text-[#A7A9B8] hover:text-[#FBFBFF] transition">
                  Multi-Provider Failover
                </a>
              </li>
            </ul>
          </div>

          {/* Link Column 2: Token Saviour */}
          <div>
            <h4 className="text-[#FBFBFF] font-bold mb-3.5 uppercase tracking-[1.1px] text-[11px]">
              TOKEN OPTIMIZER
            </h4>
            <ul className="space-y-2 text-xs">
              <li>
                <a href="#simulator" className="text-[#A7A9B8] hover:text-[#FBFBFF] transition">
                  AST Skeletonizer
                </a>
              </li>
              <li>
                <a href="#simulator" className="text-[#A7A9B8] hover:text-[#FBFBFF] transition">
                  Caveman Terse Mode
                </a>
              </li>
              <li>
                <a href="#simulator" className="text-[#A7A9B8] hover:text-[#FBFBFF] transition">
                  Whitespace Cleaner
                </a>
              </li>
              <li>
                <a href="#simulator" className="text-[#A7A9B8] hover:text-[#FBFBFF] transition">
                  Shannon Secret Mask
                </a>
              </li>
              <li>
                <a href="#simulator" className="text-[#A7A9B8] hover:text-[#FBFBFF] transition">
                  Injection Guard
                </a>
              </li>
            </ul>
          </div>

          {/* Link Column 3: Developers */}
          <div>
            <h4 className="text-[#FBFBFF] font-bold mb-3.5 uppercase tracking-[1.1px] text-[11px]">
              DEVELOPERS
            </h4>
            <ul className="space-y-2 text-xs">
              <li>
                <a href="#code" className="text-[#A7A9B8] hover:text-[#FBFBFF] transition">
                  Python SDK
                </a>
              </li>
              <li>
                <a href="#code" className="text-[#A7A9B8] hover:text-[#FBFBFF] transition">
                  TypeScript Client
                </a>
              </li>
              <li>
                <a href="#code" className="text-[#A7A9B8] hover:text-[#FBFBFF] transition">
                  OpenAI Drop-In Wire
                </a>
              </li>
              <li>
                <a href="#architecture" className="text-[#A7A9B8] hover:text-[#FBFBFF] transition">
                  Universal MCP SSE Bridge
                </a>
              </li>
              <li>
                <a href="#benchmarks" className="text-[#A7A9B8] hover:text-[#FBFBFF] transition">
                  Sub-ms Latency Matrix
                </a>
              </li>
            </ul>
          </div>

          {/* Link Column 4: Ecosystem */}
          <div>
            <h4 className="text-[#FBFBFF] font-bold mb-3.5 uppercase tracking-[1.1px] text-[11px]">
              ECOSYSTEM
            </h4>
            <ul className="space-y-2 text-xs">
              <li>
                <a
                  href="https://github.com/mrgusux/veloroute#readme"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[#A7A9B8] hover:text-[#FBFBFF] transition flex items-center space-x-1"
                >
                  <span>Documentation</span>
                  <ArrowUpRight className="w-3 h-3 text-[#5B5D6B]" />
                </a>
              </li>
              <li>
                <a
                  href="https://github.com/mrgusux/veloroute/releases"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[#A7A9B8] hover:text-[#FBFBFF] transition flex items-center space-x-1"
                >
                  <span>Releases</span>
                  <ArrowUpRight className="w-3 h-3 text-[#5B5D6B]" />
                </a>
              </li>
              <li>
                <a
                  href="https://github.com/mrgusux/veloroute/issues"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[#A7A9B8] hover:text-[#FBFBFF] transition flex items-center space-x-1"
                >
                  <span>Report Issues</span>
                  <ArrowUpRight className="w-3 h-3 text-[#5B5D6B]" />
                </a>
              </li>
              <li>
                <a href="#quickstart" className="text-[#A7A9B8] hover:text-[#FBFBFF] transition">
                  Docker Quickstart
                </a>
              </li>
              <li>
                <span className="text-[#5B5D6B] font-mono text-[11px]">MIT Open Source</span>
              </li>
            </ul>
          </div>
        </div>

        {/* Bottom Bar per DESIGN.md */}
        <div className="pt-6 border-t border-[#18181C] flex flex-col sm:flex-row items-center justify-between gap-4 text-[#5B5D6B] text-[11px] font-mono">
          <div>
            © {new Date().getFullYear()} VELOROUTE. HIGH-PERFORMANCE UNIVERSAL AI GATEWAY. MIT LICENSE.
          </div>
          <div className="flex items-center space-x-1">
            <span>ENGINEERED BY</span>
            <a
              href="https://github.com/mrgusux"
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#DFE0EA] hover:text-[#0055FF] transition font-medium"
            >
              MR. GUSU
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
}
