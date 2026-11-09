"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import {
  Zap,
  Github,
  Star,
  Menu,
  X,
  Terminal,
  Settings,
  ChevronDown,
  Layers,
  Code2,
  Activity,
} from "lucide-react";

export default function Navbar() {
  const [stars, setStars] = useState<number | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [playgroundOpen, setPlaygroundOpen] = useState(false);

  useEffect(() => {
    fetch("https://api.github.com/repos/mrgusux/veloroute")
      .then((res) => res.json())
      .then((data) => {
        if (data && typeof data.stargazers_count === "number") {
          setStars(data.stargazers_count);
        }
      })
      .catch(() => {});
  }, []);

  const navLinks = [
    { label: "Explore", href: "#features" },
    { label: "Models", href: "#models" },
    { label: "Strategies", href: "#architecture" },
    { label: "Token Saviour", href: "#simulator" },
    { label: "Benchmarks", href: "#benchmarks" },
    { label: "Docs", href: "https://github.com/mrgusux/veloroute#readme", external: true },
  ];

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-[#18181C] bg-[#000000]/90 backdrop-blur-md transition-all">
      {/* Exact 0px 24px horizontal padding per DESIGN.md */}
      <div className="w-full px-6 flex items-center justify-between h-16">
        {/* Left: Logomark & Primary Navigation */}
        <div className="flex items-center space-x-8">
          <Link href="/" className="flex items-center space-x-2.5 group">
            <div className="w-8 h-8 rounded-none bg-[#0055FF] flex items-center justify-center transition-transform group-hover:scale-105">
              <Zap className="w-4 h-4 text-[#FBFBFF]" />
            </div>
            <span className="text-base font-bold tracking-tight text-[#FBFBFF]">
              VELO<span className="text-[#0055FF]">ROUTE</span>
            </span>
          </Link>

          {/* Navigation Links */}
          <div className="hidden lg:flex items-center space-x-6">
            {navLinks.map((link) => (
              <a
                key={link.label}
                href={link.href}
                target={link.external ? "_blank" : undefined}
                rel={link.external ? "noopener noreferrer" : undefined}
                className="text-sm font-normal text-[#DFE0EA] hover:text-[#FBFBFF] transition-colors"
              >
                {link.label}
              </a>
            ))}

            {/* Playground Dropdown per DESIGN.md */}
            <div className="relative">
              <button
                onClick={() => setPlaygroundOpen(!playgroundOpen)}
                className="flex items-center space-x-1 text-sm font-normal text-[#DFE0EA] hover:text-[#FBFBFF] transition-colors"
              >
                <span>Playground</span>
                <ChevronDown className={`w-3.5 h-3.5 transition-transform ${playgroundOpen ? "rotate-180" : ""}`} />
              </button>

              {playgroundOpen && (
                <div
                  className="absolute left-0 mt-3 w-64 bg-[#0B0B0D] border border-[#18181C] shadow-2xl py-2 z-50 rounded-none"
                  onMouseLeave={() => setPlaygroundOpen(false)}
                >
                  <a
                    href="#simulator"
                    onClick={() => setPlaygroundOpen(false)}
                    className="flex items-start space-x-3 px-4 py-2.5 hover:bg-[#18181C] transition group"
                  >
                    <Layers className="w-4 h-4 text-[#0055FF] mt-0.5" />
                    <div>
                      <div className="text-xs font-semibold text-[#FBFBFF]">Token Skeletonizer</div>
                      <div className="text-[11px] text-[#A7A9B8]">Interactive AST token savings</div>
                    </div>
                  </a>
                  <a
                    href="#code"
                    onClick={() => setPlaygroundOpen(false)}
                    className="flex items-start space-x-3 px-4 py-2.5 hover:bg-[#18181C] transition group"
                  >
                    <Code2 className="w-4 h-4 text-[#0055FF] mt-0.5" />
                    <div>
                      <div className="text-xs font-semibold text-[#FBFBFF]">SDK Playground</div>
                      <div className="text-[11px] text-[#A7A9B8]">Python, TS &amp; cURL snippets</div>
                    </div>
                  </a>
                  <a
                    href="#architecture"
                    onClick={() => setPlaygroundOpen(false)}
                    className="flex items-start space-x-3 px-4 py-2.5 hover:bg-[#18181C] transition group"
                  >
                    <Activity className="w-4 h-4 text-[#0055FF] mt-0.5" />
                    <div>
                      <div className="text-xs font-semibold text-[#FBFBFF]">Circuit Breakers</div>
                      <div className="text-[11px] text-[#A7A9B8]">Live 3-state failover simulation</div>
                    </div>
                  </a>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right: Settings Icon, GitHub Star Pill & Sign In / Launch Button */}
        <div className="hidden sm:flex items-center space-x-3">
          <a
            href="https://github.com/mrgusux/veloroute"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-none text-xs font-medium bg-[#0B0B0D] hover:bg-[#111114] text-[#DFE0EA] border border-[#18181C] hover:border-white/30 transition"
            title="View repository on GitHub"
          >
            <Github className="w-3.5 h-3.5 text-[#DFE0EA]" />
            <Star className="w-3 h-3 text-[#DFE0EA]" />
            <span>Star</span>
            <span className="px-1.5 py-0.2 bg-[#18181C] text-[#FBFBFF] rounded-none font-mono text-[10px]">
              {stars !== null ? stars : "★"}
            </span>
          </a>

          <a
            href="https://github.com/mrgusux/veloroute#configuration"
            target="_blank"
            rel="noopener noreferrer"
            className="p-2 rounded-none bg-[#0B0B0D] hover:bg-[#111114] text-[#A7A9B8] hover:text-[#FBFBFF] border border-[#18181C] transition"
            title="Gateway Settings &amp; Configuration"
            aria-label="Settings"
          >
            <Settings className="w-4 h-4" />
          </a>

          <a
            href="#quickstart"
            className="inline-flex items-center space-x-1.5 px-4 py-2 rounded-none text-xs font-semibold bg-[#0055FF] hover:bg-[#0047D4] active:bg-[#003CB8] text-[#FBFBFF] transition"
          >
            <Terminal className="w-3.5 h-3.5" />
            <span className="tracking-wider uppercase">Launch Console</span>
          </a>
        </div>

        {/* Mobile menu button */}
        <div className="flex lg:hidden items-center space-x-2">
          <a
            href="https://github.com/mrgusux/veloroute"
            target="_blank"
            rel="noopener noreferrer"
            className="p-2 rounded-none bg-[#0B0B0D] border border-[#18181C] text-[#DFE0EA]"
            aria-label="GitHub Repository"
          >
            <Github className="w-4 h-4" />
          </a>
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="p-2 rounded-none bg-[#0B0B0D] text-[#DFE0EA] hover:text-[#FBFBFF] border border-[#18181C]"
            aria-label="Toggle navigation menu"
          >
            {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {/* Mobile Menu Dropdown */}
      {mobileMenuOpen && (
        <div className="lg:hidden border-b border-[#18181C] bg-[#0B0B0D] px-6 pt-3 pb-6 space-y-3">
          <div className="flex flex-col space-y-2">
            {navLinks.map((link) => (
              <a
                key={link.label}
                href={link.href}
                onClick={() => setMobileMenuOpen(false)}
                className="px-3 py-2 rounded-none text-sm font-medium text-[#DFE0EA] hover:bg-[#18181C] hover:text-[#FBFBFF] transition"
              >
                {link.label}
              </a>
            ))}
          </div>
          <div className="pt-2 border-t border-[#18181C] flex flex-col space-y-2">
            <a
              href="https://github.com/mrgusux/veloroute"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center space-x-2 px-4 py-2.5 rounded-none text-sm bg-[#111114] border border-[#18181C] text-[#DFE0EA] font-medium"
            >
              <Github className="w-4 h-4" />
              <span>Star on GitHub</span>
              <span className="font-mono text-xs text-[#A7A9B8]">★</span>
            </a>
            <a
              href="#quickstart"
              onClick={() => setMobileMenuOpen(false)}
              className="flex items-center justify-center space-x-2 px-4 py-2.5 rounded-none text-sm font-semibold bg-[#0055FF] text-[#FBFBFF]"
            >
              <Terminal className="w-4 h-4" />
              <span className="tracking-wide uppercase">Launch Console</span>
            </a>
          </div>
        </div>
      )}
    </nav>
  );
}
