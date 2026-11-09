import Link from "next/link";
import { Zap, Github, MessageSquare, LifeBuoy } from "lucide-react";

export default function Footer() {
  return (
    <footer className="border-t border-[#18181C] bg-[#0B0B0D] text-[#A7A9B8] text-xs">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-8">
          {/* Brand Info */}
          <div className="md:col-span-2 space-y-4">
            <div className="flex items-center space-x-2.5">
              <div className="w-7 h-7 rounded-none bg-[#0055FF] flex items-center justify-center">
                <Zap className="w-4 h-4 text-[#FBFBFF]" />
              </div>
              <span className="text-base font-bold text-[#FBFBFF] tracking-tight">
                VELO<span className="text-[#0055FF]">ROUTE</span>
              </span>
            </div>
            <p className="text-[#A7A9B8] text-xs max-w-md leading-relaxed">
              Enterprise Universal AI Gateway, High-Availability LLM Routing & Token-Saviour
              Optimization Engine. Zero heavy ML runtime, zero prompt retention, 100% open-source.
            </p>
            <div className="flex flex-wrap items-center gap-2 pt-2">
              <a
                href="https://github.com/mrgusux/veloroute"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-none text-xs font-mono uppercase tracking-wider text-[#FBFBFF] border border-[#18181C] hover:border-white transition bg-[#111114]"
              >
                <Github className="w-3.5 h-3.5 text-[#FBFBFF]" />
                <span>GitHub</span>
              </a>
              <span className="px-2 py-1.5 text-[10px] font-mono uppercase tracking-wider text-[#A7A9B8] border border-[#18181C] bg-[#111114]">
                MIT Licensed
              </span>
              <a
                href="https://discord.gg/veloroute"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-none text-xs font-mono uppercase tracking-wider text-[#FBFBFF] border border-[#FFFFFF] hover:bg-white hover:text-black transition bg-transparent"
              >
                <MessageSquare className="w-3.5 h-3.5" />
                <span>Join Discord</span>
              </a>
              <a
                href="mailto:support@veloroute.dev"
                className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-none text-xs font-mono uppercase tracking-wider text-[#FBFBFF] border border-[#FFFFFF] hover:bg-white hover:text-black transition bg-transparent"
              >
                <LifeBuoy className="w-3.5 h-3.5" />
                <span>Client Support</span>
              </a>
            </div>
          </div>

          {/* Architecture Links */}
          <div>
            <h4 className="text-[#FBFBFF] font-semibold mb-3 uppercase tracking-[1.1px] text-[11px]">
              Routing Engines
            </h4>
            <ul className="space-y-2">
              <li>
                <a href="#architecture" className="hover:text-[#FBFBFF] transition text-[#A7A9B8]">
                  KV-Cache Prefix Affinity
                </a>
              </li>
              <li>
                <a href="#architecture" className="hover:text-[#FBFBFF] transition text-[#A7A9B8]">
                  Sentinel Circuit Breakers
                </a>
              </li>
              <li>
                <a href="#architecture" className="hover:text-[#FBFBFF] transition text-[#A7A9B8]">
                  Speculative Hedging
                </a>
              </li>
              <li>
                <a href="#architecture" className="hover:text-[#FBFBFF] transition text-[#A7A9B8]">
                  Universal MCP Bridge
                </a>
              </li>
            </ul>
          </div>

          {/* Quick Links */}
          <div>
            <h4 className="text-[#FBFBFF] font-semibold mb-3 uppercase tracking-[1.1px] text-[11px]">
              Ecosystem
            </h4>
            <ul className="space-y-2">
              <li>
                <a
                  href="https://github.com/mrgusux/veloroute#readme"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-[#FBFBFF] transition text-[#A7A9B8]"
                >
                  Gateway Documentation
                </a>
              </li>
              <li>
                <a
                  href="https://github.com/mrgusux/veloroute/releases"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-[#FBFBFF] transition text-[#A7A9B8]"
                >
                  Changelog & Releases
                </a>
              </li>
              <li>
                <a
                  href="https://github.com/mrgusux/veloroute/issues"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-[#FBFBFF] transition text-[#A7A9B8]"
                >
                  Report Issues
                </a>
              </li>
              <li>
                <a href="#quickstart" className="hover:text-[#FBFBFF] transition text-[#A7A9B8]">
                  Deploy to Vercel
                </a>
              </li>
            </ul>
          </div>
        </div>

        {/* Bottom bar */}
        <div className="pt-8 border-t border-[#18181C] flex flex-col sm:flex-row items-center justify-between gap-4 text-[#5B5D6B] text-[11px] font-mono">
          <div>
            © {new Date().getFullYear()} VELOROUTE. BUILT WITH NEXT.JS &amp; TAILWIND CSS. MIT LICENSE.
          </div>
          <div className="flex items-center space-x-1">
            <span>AUTHORED BY</span>
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
