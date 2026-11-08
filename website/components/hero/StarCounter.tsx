"use client";

import { useState, useEffect } from "react";

export default function StarCounter() {
  const [stars, setStars] = useState<number | null>(null);

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

  return (
    <a
      href="https://github.com/mrgusux/veloroute"
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center space-x-2.5 px-5 py-3 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-100 font-medium text-sm border border-white/10 hover:border-sky-500/40 transition shadow-lg shrink-0 group"
    >
      <span>Star on GitHub</span>
      <span className="text-amber-400 font-mono">★</span>
      <span className="px-2 py-0.5 rounded bg-slate-800 text-amber-300 font-mono text-xs border border-amber-500/30 group-hover:border-amber-400/60 transition">
        {stars !== null ? stars : "★"}
      </span>
    </a>
  );
}
