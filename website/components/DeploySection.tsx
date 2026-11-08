"use client";

import { useState } from "react";
import { Terminal, Copy, Check, ExternalLink, Box, Server, ShieldCheck } from "lucide-react";

export default function DeploySection() {
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const copyText = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const dockerRunCmd =
    "docker run -d -p 8000:8000 -v veloroute_data:/data ghcr.io/mrgusux/veloroute:latest";

  const dockerComposeCmd =
    "git clone https://github.com/mrgusux/veloroute.git\ncd veloroute\ndocker compose up -d";

  const k8sCmd = "kubectl apply -f https://raw.githubusercontent.com/mrgusux/veloroute/main/deploy/k8s/deployment.yaml";

  const pipCmd = "pip install veloroute\nveloroute ui";

  const vercelDeployUrl =
    "https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2Fmrgusux%2Fveloroute&root-directory=website";

  return (
    <section id="quickstart" className="py-24 relative border-t border-white/5">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-sky-950/60 border border-sky-500/30 text-sky-400 text-xs font-mono mb-4">
            <Box className="w-3.5 h-3.5" />
            <span>Deployment Options</span>
          </div>
          <h2 className="text-3xl sm:text-5xl font-extrabold text-white tracking-tight">
            Run in 60 Seconds.
          </h2>
          <p className="mt-4 text-slate-400 text-base sm:text-lg">
            Deploy the gateway anywhere: single Docker container, production Kubernetes cluster, or
            host this Next.js site directly on Vercel for free.
          </p>
        </div>

        {/* Deploy Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-5xl mx-auto">
          {/* Card 1: 1-Click Vercel Deploy */}
          <div className="glass-panel p-6 sm:p-8 rounded-2xl border border-white/10 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 rounded-xl bg-black border border-white/20 flex items-center justify-center">
                    <svg viewBox="0 0 1155 1000" className="w-5 h-5 fill-white">
                      <path d="m577.3 0 577.4 1000H0z" />
                    </svg>
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-white">Vercel Free Hosting</h3>
                    <p className="text-xs text-slate-400">Deploy this landing page to Vercel</p>
                  </div>
                </div>
                <span className="text-[11px] font-mono text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800">
                  100% Free
                </span>
              </div>
              <p className="text-sm text-slate-300 mb-6 leading-relaxed">
                Clone and deploy this ultra-fast Next.js landing page with automatic SSL, Edge CDN,
                and zero server maintenance.
              </p>
            </div>

            <div>
              <a
                href={vercelDeployUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center justify-center space-x-2 w-full py-3 px-4 rounded-xl bg-white hover:bg-slate-200 text-black font-semibold text-sm transition shadow-lg"
              >
                <svg viewBox="0 0 1155 1000" className="w-4 h-4 fill-black">
                  <path d="m577.3 0 577.4 1000H0z" />
                </svg>
                <span>Deploy to Vercel</span>
                <ExternalLink className="w-3.5 h-3.5 ml-1" />
              </a>
            </div>
          </div>

          {/* Card 2: 1-Command Docker Run */}
          <div className="glass-panel p-6 sm:p-8 rounded-2xl border border-white/10 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 rounded-xl bg-sky-950 border border-sky-500/30 flex items-center justify-center">
                    <Box className="w-5 h-5 text-sky-400" />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-white">Docker 1-Liner</h3>
                    <p className="text-xs text-slate-400">Full Gateway & Dashboard</p>
                  </div>
                </div>
                <span className="text-[11px] font-mono text-sky-400 bg-sky-950/60 px-2 py-0.5 rounded border border-sky-800">
                  GHCR Ready
                </span>
              </div>
              <p className="text-sm text-slate-300 mb-4 leading-relaxed">
                Run the multi-provider gateway and interactive telemetry web dashboard in a secure,
                unprivileged container.
              </p>
            </div>

            <div className="bg-[#080c14] border border-white/10 rounded-xl p-3 flex items-center justify-between">
              <code className="text-xs font-mono text-sky-300 truncate mr-2">{dockerRunCmd}</code>
              <button
                onClick={() => copyText("docker", dockerRunCmd)}
                className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 shrink-0"
                title="Copy Docker Command"
              >
                {copiedId === "docker" ? (
                  <Check className="w-4 h-4 text-emerald-400" />
                ) : (
                  <Copy className="w-4 h-4" />
                )}
              </button>
            </div>
          </div>

          {/* Card 3: Docker Compose */}
          <div className="glass-panel p-6 sm:p-8 rounded-2xl border border-white/10 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 rounded-xl bg-purple-950 border border-purple-500/30 flex items-center justify-center">
                    <Server className="w-5 h-5 text-purple-400" />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-white">Docker Compose</h3>
                    <p className="text-xs text-slate-400">Persistent storage & key configs</p>
                  </div>
                </div>
                <span className="text-[11px] font-mono text-purple-400 bg-purple-950/60 px-2 py-0.5 rounded border border-purple-800">
                  Production
                </span>
              </div>
              <p className="text-sm text-slate-300 mb-4 leading-relaxed">
                Clone the repository and run with pre-configured persistent volumes, key rotation, and
                health check probes.
              </p>
            </div>

            <div className="bg-[#080c14] border border-white/10 rounded-xl p-3 flex items-center justify-between">
              <pre className="text-xs font-mono text-purple-300 whitespace-pre overflow-x-auto mr-2">
                {dockerComposeCmd}
              </pre>
              <button
                onClick={() => copyText("compose", dockerComposeCmd)}
                className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 shrink-0 self-start mt-1"
                title="Copy Compose Command"
              >
                {copiedId === "compose" ? (
                  <Check className="w-4 h-4 text-emerald-400" />
                ) : (
                  <Copy className="w-4 h-4" />
                )}
              </button>
            </div>
          </div>

          {/* Card 4: Kubernetes Helm / Manifests */}
          <div className="glass-panel p-6 sm:p-8 rounded-2xl border border-white/10 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 rounded-xl bg-emerald-950 border border-emerald-500/30 flex items-center justify-center">
                    <ShieldCheck className="w-5 h-5 text-emerald-400" />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-white">Enterprise Kubernetes</h3>
                    <p className="text-xs text-slate-400">deploy/k8s/ manifests</p>
                  </div>
                </div>
                <span className="text-[11px] font-mono text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800">
                  Cloud Native
                </span>
              </div>
              <p className="text-sm text-slate-300 mb-4 leading-relaxed">
                Deploy to AWS EKS, GCP GKE, or self-hosted k8s with zero-privilege securityContext,
                rolling updates, and PVC storage.
              </p>
            </div>

            <div className="bg-[#080c14] border border-white/10 rounded-xl p-3 flex items-center justify-between">
              <code className="text-xs font-mono text-emerald-300 truncate mr-2">
                kubectl apply -f deploy/k8s/
              </code>
              <button
                onClick={() => copyText("k8s", "kubectl apply -f deploy/k8s/")}
                className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 shrink-0"
                title="Copy K8s Command"
              >
                {copiedId === "k8s" ? (
                  <Check className="w-4 h-4 text-emerald-400" />
                ) : (
                  <Copy className="w-4 h-4" />
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
