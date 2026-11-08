"use client";

import { useState } from "react";
import { Copy, Check } from "lucide-react";

export default function DockerCopyPill() {
  const [copied, setCopied] = useState(false);
  const dockerCommand =
    "docker run -d -p 8000:8000 -v veloroute_data:/data ghcr.io/mrgusux/veloroute:latest";

  const handleCopy = () => {
    navigator.clipboard.writeText(dockerCommand);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex items-center bg-slate-950/90 border border-sky-500/40 hover:border-sky-400/80 rounded-xl p-1.5 backdrop-blur-lg shadow-xl shadow-sky-500/10 max-w-xl w-full sm:w-auto transition-all">
      <div className="flex items-center space-x-2 px-3 py-1.5 font-mono text-xs text-sky-300 select-all overflow-x-auto whitespace-nowrap">
        <span className="text-emerald-400 select-none">$</span>
        <span>{dockerCommand}</span>
      </div>
      <button
        onClick={handleCopy}
        className="flex items-center space-x-1.5 px-3 py-2 rounded-lg bg-sky-500/20 hover:bg-sky-500/30 text-sky-300 font-mono text-xs font-semibold border border-sky-500/30 transition shrink-0 ml-auto"
        title="Copy Docker command"
      >
        {copied ? (
          <>
            <Check className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-emerald-400">Copied!</span>
          </>
        ) : (
          <>
            <Copy className="w-3.5 h-3.5" />
            <span>Copy</span>
          </>
        )}
      </button>
    </div>
  );
}
