import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://veloroute-tau.vercel.app"),
  title: "VeloRoute — High-Performance Universal AI Gateway & Token-Saviour Engine",
  description:
    "Enterprise AI Gateway with sub-millisecond multi-provider routing, Sentinel circuit breakers, AST token context compression, KV-cache prefix affinity, and zero retention.",
  keywords: [
    "AI Gateway",
    "LLM Router",
    "OpenAI",
    "Anthropic Claude",
    "Google Gemini",
    "Token Optimization",
    "AST Skeletonizer",
    "Circuit Breaker",
    "KV Cache Affinity",
    "Model Context Protocol",
  ],
  authors: [{ name: "Mr. Gusu", url: "https://github.com/mrgusux" }],
  openGraph: {
    title: "VeloRoute — Enterprise Universal AI Gateway",
    description:
      "Route across OpenAI, Anthropic, Gemini, Groq, and local Ollama with < 0.8ms overhead and native AST token compression.",
    url: "https://veloroute-tau.vercel.app",
    siteName: "VeloRoute",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "VeloRoute — High-Performance Universal AI Gateway",
    description:
      "Enterprise AI Gateway with sub-millisecond multi-provider routing, Sentinel circuit breakers, and AST token compression.",
  },
  icons: {
    icon: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚡</text></svg>",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark scroll-smooth">
      <body className="bg-[#07090e] text-slate-100 antialiased selection:bg-sky-500/30 selection:text-sky-300">
        {children}
      </body>
    </html>
  );
}
