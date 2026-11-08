"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { Zap, Github, Star, Menu, X, Terminal, ArrowUpRight } from "lucide-react";

export default function Navbar() {
  const [stars, setStars] = useState<number | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    // Attempt to fetch live star count from GitHub API with graceful fallback
    fetch("https://api.github.com/repos/mrgusux/veloroute")
      .then((res) => res.json())
      .then((data) => {
        if (data && typeof data.stargazers_count === "number") {
          setStars(data.stargazers_count);
        }
      })
      .catch(() => {
        // Fallback to null (or fallback value)
      });
  }, []);

  const navLinks = [
    { label: "Features", href: "#features" },
    { label: "Token Saviour", href: "#simulator" },
    { label: "Architecture", href: "#architecture" },
    { label: "SDKs", href: "#code" },
    { label: "Benchmarks", href: "#benchmarks" },
    { label: "Quickstart", href: "#quickstart" },
  ];

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-white/10 bg-[#07090e]/80 backdrop-blur-xl transition-all">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo & Version */}
          <div className="flex items-center space-x-3">
            <Link href="/" className="flex items-center space-x-2.5 group">
              <div className="w-9 h-9 rounded-lg bg-gradient-to-tr from-sky-500 to-emerald-400 p-[1px] shadow-lg shadow-sky-500/20 group-hover:shadow-sky-500/40 transition">
                <div className="w-full h-full bg-[#07090e] rounded-[7px] flex items-center justify-center">
                  <Zap className="w-5 h-5 text-sky-400 group-hover:scale-110 transition-transform" />
                </div>
              </div>
              <span className="text-xl font-bold tracking-tight text-white group-hover:text-sky-300 transition-colors">
                Velo<span className="text-sky-400">Route</span>
              </span>
            </Link>
            <span className="hidden sm:inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-medium bg-sky-950/60 text-sky-400 border border-sky-800/40">
              v1.0.0
            </span>
            <span className="hidden md:inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-medium bg-emerald-950/60 text-emerald-400 border border-emerald-800/40">
              Zero-Heavy-ML
            </span>
          </div>

          {/* Desktop Navigation Links */}
          <div className="hidden lg:flex items-center space-x-7">
            {navLinks.map((link) => (
              <a
                key={link.label}
                href={link.href}
                className="text-sm font-medium text-slate-300 hover:text-white transition-colors"
              >
                {link.label}
              </a>
            ))}
          </div>

          {/* Right Action Buttons */}
          <div className="hidden sm:flex items-center space-x-3">
            <a
              href="https://github.com/mrgusux/veloroute"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-900 hover:bg-slate-800 text-slate-200 border border-white/10 hover:border-slate-600 transition"
              title="View repository on GitHub"
            >
              <Github className="w-4 h-4 text-slate-300" />
              <Star className="w-3.5 h-3.5 text-amber-400 fill-amber-400" />
              <span>Star</span>
              <span className="px-1.5 py-0.2 bg-slate-800 text-slate-300 rounded font-mono text-[11px]">
                {stars !== null ? stars : "★"}
              </span>
            </a>

            <a
              href="#quickstart"
              className="inline-flex items-center space-x-1.5 px-4 py-2 rounded-lg text-xs font-semibold bg-gradient-to-r from-sky-500 to-emerald-500 hover:from-sky-400 hover:to-emerald-400 text-slate-950 font-mono shadow-md shadow-sky-500/20 hover:shadow-sky-500/40 transition active:scale-95"
            >
              <Terminal className="w-3.5 h-3.5" />
              <span>Deploy Now</span>
            </a>
          </div>

          {/* Mobile menu button */}
          <div className="flex lg:hidden items-center space-x-2">
            <a
              href="https://github.com/mrgusux/veloroute"
              target="_blank"
              rel="noopener noreferrer"
              className="p-2 rounded-lg bg-slate-900 border border-white/10 text-slate-300"
              aria-label="GitHub Repository"
            >
              <Github className="w-4 h-4" />
            </a>
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="p-2 rounded-lg bg-slate-900 text-slate-300 hover:text-white border border-white/10"
              aria-label="Toggle navigation menu"
            >
              {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile Menu Dropdown */}
      {mobileMenuOpen && (
        <div className="lg:hidden border-b border-white/10 bg-[#0c1017]/95 backdrop-blur-xl px-4 pt-3 pb-6 space-y-3">
          <div className="flex flex-col space-y-2">
            {navLinks.map((link) => (
              <a
                key={link.label}
                href={link.href}
                onClick={() => setMobileMenuOpen(false)}
                className="px-3 py-2 rounded-md text-sm font-medium text-slate-200 hover:bg-slate-800 hover:text-sky-400 transition"
              >
                {link.label}
              </a>
            ))}
          </div>
          <div className="pt-2 border-t border-white/10 flex flex-col space-y-2">
            <a
              href="https://github.com/mrgusux/veloroute"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center space-x-2 px-4 py-2.5 rounded-lg text-sm bg-slate-900 border border-white/10 text-slate-200 font-medium"
            >
              <Github className="w-4 h-4" />
              <span>Star on GitHub</span>
              <span className="font-mono text-xs text-amber-400">★</span>
            </a>
            <a
              href="#quickstart"
              onClick={() => setMobileMenuOpen(false)}
              className="flex items-center justify-center space-x-2 px-4 py-2.5 rounded-lg text-sm font-semibold bg-gradient-to-r from-sky-500 to-emerald-500 text-slate-950 font-mono"
            >
              <Terminal className="w-4 h-4" />
              <span>Deploy Now</span>
            </a>
          </div>
        </div>
      )}
    </nav>
  );
}
