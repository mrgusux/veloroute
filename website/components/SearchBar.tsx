"use client";

import { useState } from "react";
import { Search, ArrowRight, X } from "lucide-react";

interface SearchBarProps {
  onSearch?: (query: string) => void;
  initialQuery?: string;
}

export default function SearchBar({ onSearch, initialQuery = "" }: SearchBarProps) {
  const [query, setQuery] = useState(initialQuery);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (onSearch) {
      onSearch(query);
    }
    const modelSection = document.getElementById("models");
    if (modelSection) {
      modelSection.scrollIntoView({ behavior: "smooth" });
    }
  };

  const handleClear = () => {
    setQuery("");
    if (onSearch) {
      onSearch("");
    }
  };

  return (
    <div className="w-full bg-[#000000] py-6 border-b border-[#18181C]">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-8 lg:px-[120px]">
        <form onSubmit={handleSubmit} className="relative flex items-center">
          <div className="relative flex-1 flex items-center bg-[#0B0B0D] border border-[#18181C] hover:border-[#25252C] focus-within:border-white/30 transition-colors h-14">
            <div className="pl-4 pr-2 text-[#5B5D6B]">
              <Search className="w-4 h-4" />
            </div>
            <input
              type="text"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                if (onSearch) onSearch(e.target.value);
              }}
              placeholder="Search 80+ AI models, routing strategies, or MCP tools (e.g. claude-3-7, deepseek-r1, hedging)..."
              className="w-full bg-transparent text-sm text-[#FBFBFF] placeholder-[#5B5D6B] focus:outline-none font-normal"
            />
            {query && (
              <button
                type="button"
                onClick={handleClear}
                className="p-2 text-[#5B5D6B] hover:text-[#DFE0EA] transition"
                aria-label="Clear search"
              >
                <X className="w-4 h-4" />
              </button>
            )}
            <button
              type="submit"
              className="h-full bg-[#0055FF] hover:bg-[#0047D4] active:bg-[#003CB8] text-[#FBFBFF] px-6 text-sm font-medium flex items-center space-x-2 transition-colors rounded-none shrink-0"
            >
              <span>Find</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
