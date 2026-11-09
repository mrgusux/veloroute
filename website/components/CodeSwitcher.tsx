"use client";

import { useState } from "react";
import { Terminal, Copy, Check, Code2, ArrowUpRight } from "lucide-react";

interface CodeSnippet {
  id: string;
  name: string;
  lang: string;
  desc: string;
  code: string;
}

const SNIPPETS: CodeSnippet[] = [
  {
    id: "openai",
    name: "Python (OpenAI SDK)",
    lang: "python",
    desc: "Seamless drop-in for OpenAI SDK. Simply repoint base_url to VeloRoute.",
    code: `import os
from openai import OpenAI

# Zero code modifications: just point base_url to VeloRoute!
client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key=os.environ.get("VELOROUTE_KEY", "sk-velo-prod-key"),
)

# Route with intelligent fallbacks & AST compression
response = client.chat.completions.create(
    model="smart",  # Or 'gpt-4o', 'claude-3-5-sonnet', 'deepseek-r1'
    messages=[
        {"role": "system", "content": "You are a lead security architect."},
        {"role": "user", "content": "/terse Audit this auth flow for vulnerabilities."},
    ],
    temperature=0.2,
)

print(response.choices[0].message.content)`,
  },
  {
    id: "anthropic",
    name: "Python (Anthropic SDK)",
    lang: "python",
    desc: "Native Anthropic /v1/messages compatibility with streaming & prompt cache.",
    code: `import os
from anthropic import Anthropic

# VeloRoute transparently speaks native Anthropic protocol
client = Anthropic(
    base_url="http://localhost:8000",
    api_key=os.environ.get("VELOROUTE_KEY", "sk-velo-prod-key"),
)

message = client.messages.create(
    model="claude-3-5-sonnet",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "Refactor this async pipeline using Tokio in Rust."}
    ],
)

print(message.content[0].text)`,
  },
  {
    id: "typescript",
    name: "TypeScript (Node.js)",
    lang: "typescript",
    desc: "100% drop-in for official OpenAI & Anthropic Node.js SDKs in Next.js and backend apps.",
    code: `import OpenAI from "openai";

// Repoint baseURL to your VeloRoute gateway:
const client = new OpenAI({
  baseURL: "http://localhost:8000/v1",
  apiKey: process.env.VELOROUTE_KEY || "sk-velo-prod-key",
});

const response = await client.chat.completions.create({
  model: "smart",
  messages: [
    { role: "system", content: "You are an expert systems architect." },
    { role: "user", content: "/terse Profile memory allocation in this Tokio service." },
  ],
});

console.log(response.choices[0]?.message.content);`,
  },
  {
    id: "curl",
    name: "Raw cURL / HTTP",
    lang: "bash",
    desc: "Universal standard HTTP API compatible with any language, bash, or microservice.",
    code: `curl -X POST http://localhost:8000/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer sk-velo-prod-key" \\
  -d '{
    "model": "fast",
    "messages": [
      {
        "role": "user",
        "content": "/fast Compute the time complexity of Ford-Fulkerson algorithm."
      }
    ],
    "stream": true
  }'`,
  },
  {
    id: "claude-code",
    name: "Claude Code / Agent CLI",
    lang: "bash",
    desc: "Point Claude Code CLI, Cursor, or Cline to VeloRoute with zero config.",
    code: `# Configure Claude Code CLI to route through VeloRoute gateway
export ANTHROPIC_BASE_URL="http://localhost:8000"
export ANTHROPIC_API_KEY="sk-velo-prod-key"

# Launch Claude Code agent with Sentinel failover & AST compression active!
claude`,
  },
];

export default function CodeSwitcher() {
  const [activeTab, setActiveTab] = useState<string>("openai");
  const [copied, setCopied] = useState<boolean>(false);

  const current = SNIPPETS.find((s) => s.id === activeTab) || SNIPPETS[0];

  const handleCopy = () => {
    navigator.clipboard.writeText(current.code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <section id="code" className="py-24 relative border-t border-[#18181C] bg-[#000000]">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-8 lg:px-[120px]">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-none bg-[#111114] border border-[#18181C] text-[#0055FF] text-[11px] font-mono uppercase tracking-widest mb-4">
            <Code2 className="w-3.5 h-3.5 text-[#0055FF]" />
            <span>DROP-IN COMPATIBILITY</span>
          </div>
          <h2 className="text-3xl sm:text-5xl font-bold text-[#FBFBFF] tracking-tight">
            1 Line of Code to Switch.
          </h2>
          <p className="mt-4 text-[#A7A9B8] text-base sm:text-lg">
            No proprietary SDKs. Use the official OpenAI, Anthropic, or Ollama clients you already
            know. Simply repoint your <code className="text-[#0055FF] font-mono">base_url</code>.
          </p>
        </div>

        {/* Code Box Container */}
        <div className="max-w-4xl mx-auto rounded-none bg-[#0B0B0D] border border-[#18181C] overflow-hidden shadow-none">
          {/* Top Bar with Tabs and Copy Button */}
          <div className="flex flex-wrap items-center justify-between px-4 py-3 bg-[#000000] border-b border-[#18181C] gap-2">
            <div className="flex items-center space-x-1.5 overflow-x-auto no-scrollbar">
              {SNIPPETS.map((snip) => (
                <button
                  key={snip.id}
                  onClick={() => setActiveTab(snip.id)}
                  className={`px-3 py-1.5 rounded-none text-xs font-mono uppercase tracking-wider transition whitespace-nowrap ${
                    activeTab === snip.id
                      ? "bg-[#0055FF] text-[#FBFBFF]"
                      : "text-[#A7A9B8] hover:text-[#FBFBFF]"
                  }`}
                >
                  {snip.name}
                </button>
              ))}
            </div>

            <button
              onClick={handleCopy}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-none bg-[#111114] hover:bg-[#18181C] text-[#DFE0EA] text-xs font-mono uppercase tracking-wider border border-[#18181C] transition"
              title="Copy code to clipboard"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-[#0055FF]" />
                  <span className="text-[#0055FF]">COPIED</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  <span>Copy Code</span>
                </>
              )}
            </button>
          </div>

          {/* Description sub-strip */}
          <div className="px-5 py-2.5 bg-[#111114] border-b border-[#18181C] text-xs text-[#A7A9B8] flex items-center justify-between">
            <span>{current.desc}</span>
            <span className="text-[10px] font-mono text-[#0055FF] uppercase tracking-wider font-bold">
              {current.lang}
            </span>
          </div>

          {/* Code Content */}
          <div className="p-5 sm:p-6 bg-[#0B0B0D] overflow-x-auto">
            <pre className="font-mono text-xs sm:text-sm text-[#DFE0EA] leading-relaxed whitespace-pre">
              {current.code}
            </pre>
          </div>
        </div>
      </div>
    </section>
  );
}
