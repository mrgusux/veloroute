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
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-[#18181C] bg-[#000000]/90 backdrop-blur-md transition-all">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo & Version */}
          <div className="flex items-center space-x-3">
            <Link href="/" className="flex items-center space-x-2.5 group">
              <div className="w-8 h-8 rounded-none bg-[#0055FF] flex items-center justify-center transition-transform group-hover:scale-105">
                <Zap className="w-4 h-4 text-[#FBFBFF]" />
              </div>
              <span className="text-lg font-bold tracking-tight text-[#FBFBFF] group-hover:text-white transition-colors">
                VELO<span className="text-[#0055FF]">ROUTE</span>
              </span>
            </Link>
            <span className="hidden sm:inline-flex items-center px-2 py-0.5 rounded-none text-[10px] font-mono font-bold tracking-wider bg-[#111114] text-[#A7A9B8] border border-[#18181C] uppercase">
              v1.0.0
            </span>
            <span className="hidden md:inline-flex items-center px-2 py-0.5 rounded-none text-[10px] font-mono font-bold tracking-wider bg-[#111114] text-[#0055FF] border border-[#18181C] uppercase">
              ZERO-HEAVY-ML
            </span>
          </div>

          {/* Desktop Navigation Links */}
          <div className="hidden lg:flex items-center space-x-7">
            {navLinks.map((link) => (
              <a
                key={link.label}
                href={link.href}
                className="text-sm font-normal text-[#DFE0EA] hover:text-[#FBFBFF] transition-colors"
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
              className="inline-flex items-center space-x-1.5 px-3 py-2 rounded-none text-xs font-medium bg-[#0B0B0D] hover:bg-[#111114] text-[#DFE0EA] border border-[#18181C] hover:border-white/30 transition"
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
              href="#quickstart"
              className="inline-flex items-center space-x-1.5 px-4 py-2 rounded-none text-xs font-semibold bg-[#0055FF] hover:bg-[#0044CC] text-[#FBFBFF] transition active:scale-95"
            >
              <Terminal className="w-3.5 h-3.5" />
              <span className="tracking-wide uppercase">Deploy Now</span>
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
      </div>

      {/* Mobile Menu Dropdown */}
      {mobileMenuOpen && (
        <div className="lg:hidden border-b border-[#18181C] bg-[#0B0B0D] px-4 pt-3 pb-6 space-y-3">
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
              <span className="tracking-wide uppercase">Deploy Now</span>
            </a>
          </div>
        </div>
      )}
    </nav>
  );
}
