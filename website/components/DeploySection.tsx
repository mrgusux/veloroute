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

  const helmCmd = "helm install veloroute ./deploy/helm/veloroute";
  const k8sCmd = "kubectl apply -f deploy/k8s/";
  const pipCmd = "pip install -e . && veloroute ui";

  const vercelDeployUrl =
    "https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2Fmrgusux%2Fveloroute&root-directory=website";

  return (
    <section id="quickstart" className="py-24 relative border-t border-[#18181C] bg-[#000000]">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-8 lg:px-[120px]">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-none bg-[#111114] border border-[#18181C] text-[#0055FF] text-[11px] font-mono uppercase tracking-widest mb-4">
            <Box className="w-3.5 h-3.5 text-[#0055FF]" />
            <span>DEPLOYMENT OPTIONS</span>
          </div>
          <h2 className="text-3xl sm:text-5xl font-bold text-[#FBFBFF] tracking-tight">
            Run in 60 Seconds.
          </h2>
          <p className="mt-4 text-[#A7A9B8] text-base sm:text-lg">
            Deploy the gateway anywhere: single Docker container, production Kubernetes cluster, or
            host this Next.js site directly on Vercel for free.
          </p>
        </div>

        {/* Deploy Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-5xl mx-auto">
          {/* Card 1: 1-Click Vercel Deploy */}
          <div className="bg-[#0B0B0D] p-6 sm:p-8 rounded-none border border-[#18181C] flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 rounded-none bg-[#000000] border border-[#18181C] flex items-center justify-center">
                    <svg viewBox="0 0 1155 1000" className="w-5 h-5 fill-white">
                      <path d="m577.3 0 577.4 1000H0z" />
                    </svg>
                  </div>
                  <div>
                    <h3 className="text-base font-semibold text-[#FBFBFF]">Vercel Edge Hosting</h3>
                    <p className="text-xs text-[#A7A9B8]">Deploy this landing page to Vercel</p>
                  </div>
                </div>
                <span className="text-[10px] font-mono uppercase tracking-wider text-[#0055FF] bg-[#18181C] px-2 py-0.5 rounded-none border border-[#18181C]">
                  100% Free
                </span>
              </div>
              <p className="text-sm text-[#DFE0EA] mb-6 leading-relaxed">
                Clone and deploy this ultra-fast Next.js landing page with automatic SSL, Edge CDN,
                and zero server maintenance.
              </p>
            </div>

            <div>
              <a
                href={vercelDeployUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center justify-center space-x-2 w-full py-3 px-4 rounded-none bg-[#0055FF] hover:bg-[#0044CC] text-[#FBFBFF] font-medium text-xs uppercase tracking-wider transition"
              >
                <svg viewBox="0 0 1155 1000" className="w-3.5 h-3.5 fill-white">
                  <path d="m577.3 0 577.4 1000H0z" />
                </svg>
                <span>Deploy to Vercel</span>
                <ExternalLink className="w-3.5 h-3.5 ml-1" />
              </a>
            </div>
          </div>

          {/* Card 2: 1-Command Docker Run */}
          <div className="bg-[#0B0B0D] p-6 sm:p-8 rounded-none border border-[#18181C] flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 rounded-none bg-[#111114] border border-[#18181C] flex items-center justify-center">
                    <Box className="w-5 h-5 text-[#0055FF]" />
                  </div>
                  <div>
                    <h3 className="text-base font-semibold text-[#FBFBFF]">Docker 1-Liner</h3>
                    <p className="text-xs text-[#A7A9B8]">Full Gateway & Dashboard</p>
                  </div>
                </div>
                <span className="text-[10px] font-mono uppercase tracking-wider text-[#A7A9B8] bg-[#18181C] px-2 py-0.5 rounded-none border border-[#18181C]">
                  GHCR Ready
                </span>
              </div>
              <p className="text-sm text-[#DFE0EA] mb-4 leading-relaxed">
                Run the multi-provider gateway and interactive telemetry web dashboard in a secure,
                unprivileged container.
              </p>
            </div>

            <div className="bg-[#000000] border border-[#18181C] rounded-none p-3 flex items-center justify-between">
              <code className="text-xs font-mono text-[#DFE0EA] truncate mr-2">{dockerRunCmd}</code>
              <button
                onClick={() => copyText("docker", dockerRunCmd)}
                className="p-1.5 rounded-none bg-[#111114] hover:bg-[#18181C] text-[#DFE0EA] border border-[#18181C] shrink-0"
                title="Copy Docker Command"
              >
                {copiedId === "docker" ? (
                  <Check className="w-4 h-4 text-[#0055FF]" />
                ) : (
                  <Copy className="w-4 h-4" />
                )}
              </button>
            </div>
          </div>

          {/* Card 3: Docker Compose */}
          <div className="bg-[#0B0B0D] p-6 sm:p-8 rounded-none border border-[#18181C] flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 rounded-none bg-[#111114] border border-[#18181C] flex items-center justify-center">
                    <Server className="w-5 h-5 text-[#0055FF]" />
                  </div>
                  <div>
                    <h3 className="text-base font-semibold text-[#FBFBFF]">Docker Compose</h3>
                    <p className="text-xs text-[#A7A9B8]">Persistent storage & key configs</p>
                  </div>
                </div>
                <span className="text-[10px] font-mono uppercase tracking-wider text-[#A7A9B8] bg-[#18181C] px-2 py-0.5 rounded-none border border-[#18181C]">
                  Production
                </span>
              </div>
              <p className="text-sm text-[#DFE0EA] mb-4 leading-relaxed">
                Clone the repository and run with pre-configured persistent volumes, key rotation, and
                health check probes.
              </p>
            </div>

            <div className="bg-[#000000] border border-[#18181C] rounded-none p-3 flex items-center justify-between">
              <pre className="text-xs font-mono text-[#DFE0EA] whitespace-pre overflow-x-auto mr-2">
                {dockerComposeCmd}
              </pre>
              <button
                onClick={() => copyText("compose", dockerComposeCmd)}
                className="p-1.5 rounded-none bg-[#111114] hover:bg-[#18181C] text-[#DFE0EA] border border-[#18181C] shrink-0 self-start mt-1"
                title="Copy Compose Command"
              >
                {copiedId === "compose" ? (
                  <Check className="w-4 h-4 text-[#0055FF]" />
                ) : (
                  <Copy className="w-4 h-4" />
                )}
              </button>
            </div>
          </div>

          {/* Card 4: Kubernetes Helm / Manifests */}
          <div className="bg-[#0B0B0D] p-6 sm:p-8 rounded-none border border-[#18181C] flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 rounded-none bg-[#111114] border border-[#18181C] flex items-center justify-center">
                    <ShieldCheck className="w-5 h-5 text-[#0055FF]" />
                  </div>
                  <div>
                    <h3 className="text-base font-semibold text-[#FBFBFF]">Enterprise Kubernetes</h3>
                    <p className="text-xs text-[#A7A9B8]">deploy/k8s/ manifests</p>
                  </div>
                </div>
                <span className="text-[10px] font-mono uppercase tracking-wider text-[#0055FF] bg-[#18181C] px-2 py-0.5 rounded-none border border-[#18181C]">
                  Cloud Native
                </span>
              </div>
              <p className="text-sm text-[#DFE0EA] mb-4 leading-relaxed">
                Deploy to AWS EKS, GCP GKE, or k8s via Helm chart or standard declarative manifests
                with zero-privilege securityContext and PVC persistence.
              </p>
            </div>

            <div className="space-y-2">
              <div className="bg-[#000000] border border-[#18181C] rounded-none p-3 flex items-center justify-between">
                <code className="text-xs font-mono text-[#DFE0EA] truncate mr-2">
                  {helmCmd}
                </code>
                <button
                  onClick={() => copyText("helm", helmCmd)}
                  className="p-1.5 rounded-none bg-[#111114] hover:bg-[#18181C] text-[#DFE0EA] border border-[#18181C] shrink-0"
                  title="Copy Helm Command"
                >
                  {copiedId === "helm" ? (
                    <Check className="w-4 h-4 text-[#0055FF]" />
                  ) : (
                    <Copy className="w-4 h-4" />
                  )}
                </button>
              </div>
              <div className="bg-[#000000] border border-[#18181C] rounded-none p-3 flex items-center justify-between">
                <code className="text-xs font-mono text-[#A7A9B8] truncate mr-2">
                  {k8sCmd}
                </code>
                <button
                  onClick={() => copyText("k8s", k8sCmd)}
                  className="p-1.5 rounded-none bg-[#111114] hover:bg-[#18181C] text-[#DFE0EA] border border-[#18181C] shrink-0"
                  title="Copy K8s Command"
                >
                  {copiedId === "k8s" ? (
                    <Check className="w-4 h-4 text-[#0055FF]" />
                  ) : (
                    <Copy className="w-4 h-4" />
                  )}
                </button>
              </div>
            </div>
          </div>

          {/* Card 5: Python PIP Quickstart */}
          <div className="md:col-span-2 bg-[#0B0B0D] p-6 sm:p-8 rounded-none border border-[#18181C] flex flex-col md:flex-row items-center justify-between gap-6">
            <div>
              <div className="flex items-center space-x-3 mb-2">
                <div className="w-8 h-8 rounded-none bg-[#111114] border border-[#18181C] flex items-center justify-center">
                  <Terminal className="w-4 h-4 text-[#0055FF]" />
                </div>
                <h3 className="text-base font-semibold text-[#FBFBFF]">Local Python / CLI Quickstart</h3>
                <span className="text-[10px] font-mono uppercase tracking-wider text-[#0055FF] bg-[#18181C] px-2 py-0.5 rounded-none border border-[#18181C]">
                  PyPI Ready
                </span>
              </div>
              <p className="text-xs text-[#A7A9B8] max-w-xl leading-relaxed">
                Run natively in Python 3.11+ virtual environments with built-in doctor diagnostics,
                recipe configurations, and zero heavy ML dependencies.
              </p>
            </div>

            <div className="bg-[#000000] border border-[#18181C] rounded-none p-3 flex items-center justify-between w-full md:w-auto md:min-w-[340px]">
              <code className="text-xs font-mono text-[#DFE0EA] mr-3">{pipCmd}</code>
              <button
                onClick={() => copyText("pip", pipCmd)}
                className="p-1.5 rounded-none bg-[#111114] hover:bg-[#18181C] text-[#DFE0EA] border border-[#18181C] shrink-0"
                title="Copy PIP Command"
              >
                {copiedId === "pip" ? (
                  <Check className="w-4 h-4 text-[#0055FF]" />
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
