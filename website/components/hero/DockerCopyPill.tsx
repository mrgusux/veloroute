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
    <div className="flex items-center bg-[#0B0B0D] border border-[#18181C] hover:border-[#0055FF] rounded-none p-1.5 shadow-none max-w-xl w-full sm:w-auto transition-all">
      <div className="flex items-center space-x-2 px-3 py-1.5 font-mono text-xs text-[#DFE0EA] select-all overflow-x-auto whitespace-nowrap">
        <span className="text-[#0055FF] select-none font-bold">$</span>
        <span>{dockerCommand}</span>
      </div>
      <button
        onClick={handleCopy}
        className="flex items-center space-x-1.5 px-3 py-2 rounded-none bg-[#0055FF] hover:bg-[#0044CC] text-[#FBFBFF] font-mono text-xs font-semibold transition shrink-0 ml-auto"
        title="Copy Docker command"
      >
        {copied ? (
          <>
            <Check className="w-3.5 h-3.5 text-[#FBFBFF]" />
            <span className="text-[#FBFBFF]">COPIED</span>
          </>
        ) : (
          <>
            <Copy className="w-3.5 h-3.5" />
            <span className="uppercase tracking-wider text-[11px]">Copy</span>
          </>
        )}
      </button>
    </div>
  );
}
