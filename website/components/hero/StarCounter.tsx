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
      className="inline-flex items-center space-x-2.5 px-5 py-3 rounded-none bg-transparent hover:bg-white/5 text-[#FBFBFF] font-medium text-xs uppercase tracking-wider border border-[#18181C] hover:border-white transition shrink-0 group"
    >
      <span>Star on GitHub</span>
      <span className="text-[#DFE0EA] font-mono">★</span>
      <span className="px-2 py-0.5 rounded-none bg-[#18181C] text-[#FBFBFF] font-mono text-[11px] border border-[#18181C] group-hover:border-white/40 transition">
        {stars !== null ? stars : "★"}
      </span>
    </a>
  );
}
