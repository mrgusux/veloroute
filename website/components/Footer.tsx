import Link from "next/link";
import { Zap, Github, Heart } from "lucide-react";

export default function Footer() {
  return (
    <footer className="border-t border-white/10 bg-[#05070a] text-slate-400 text-xs">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-8">
          {/* Brand Info */}
          <div className="md:col-span-2 space-y-3">
            <div className="flex items-center space-x-2.5">
              <div className="w-7 h-7 rounded-lg bg-sky-500/20 border border-sky-500/40 flex items-center justify-center">
                <Zap className="w-4 h-4 text-sky-400" />
              </div>
              <span className="text-base font-bold text-white tracking-tight">
                Velo<span className="text-sky-400">Route</span>
              </span>
            </div>
            <p className="text-slate-400 text-xs max-w-md leading-relaxed">
              Enterprise Universal AI Gateway, High-Availability LLM Routing & Token-Saviour
              Optimization Engine. Zero heavy ML runtime, zero prompt retention, 100% open-source.
            </p>
            <div className="pt-2 flex items-center space-x-3 text-slate-400">
              <a
                href="https://github.com/mrgusux/veloroute"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-white transition flex items-center space-x-1"
              >
                <Github className="w-4 h-4" />
                <span>GitHub</span>
              </a>
              <span>•</span>
              <span className="font-mono text-emerald-400">MIT Licensed</span>
            </div>
          </div>

          {/* Architecture Links */}
          <div>
            <h4 className="text-white font-semibold mb-3 uppercase tracking-wider text-[11px]">
              Routing Engines
            </h4>
            <ul className="space-y-2">
              <li>
                <a href="#architecture" className="hover:text-sky-400 transition">
                  KV-Cache Prefix Affinity
                </a>
              </li>
              <li>
                <a href="#architecture" className="hover:text-sky-400 transition">
                  Sentinel Circuit Breakers
                </a>
              </li>
              <li>
                <a href="#architecture" className="hover:text-sky-400 transition">
                  Speculative Hedging
                </a>
              </li>
              <li>
                <a href="#architecture" className="hover:text-sky-400 transition">
                  Universal MCP Bridge
                </a>
              </li>
            </ul>
          </div>

          {/* Quick Links */}
          <div>
            <h4 className="text-white font-semibold mb-3 uppercase tracking-wider text-[11px]">
              Ecosystem
            </h4>
            <ul className="space-y-2">
              <li>
                <a
                  href="https://github.com/mrgusux/veloroute#readme"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-sky-400 transition"
                >
                  Gateway Documentation
                </a>
              </li>
              <li>
                <a
                  href="https://github.com/mrgusux/veloroute/releases"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-sky-400 transition"
                >
                  Changelog & Releases
                </a>
              </li>
              <li>
                <a
                  href="https://github.com/mrgusux/veloroute/issues"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-sky-400 transition"
                >
                  Report Issues
                </a>
              </li>
              <li>
                <a href="#quickstart" className="hover:text-sky-400 transition">
                  Deploy to Vercel
                </a>
              </li>
            </ul>
          </div>
        </div>

        {/* Bottom bar */}
        <div className="pt-8 border-t border-white/5 flex flex-col sm:flex-row items-center justify-between gap-4 text-slate-500 text-[11px]">
          <div>
            © {new Date().getFullYear()} VeloRoute. Built with Next.js & Tailwind CSS. Open-source under MIT License.
          </div>
          <div className="flex items-center space-x-1">
            <span>Authored by</span>
            <a
              href="https://github.com/mrgusux"
              target="_blank"
              rel="noopener noreferrer"
              className="text-slate-400 hover:text-sky-400 transition font-medium"
            >
              Mr. Gusu
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
}
