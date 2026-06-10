"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, Brain, Server, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

async function fetchHealth() {
  const res = await fetch("http://localhost:8000/health");
  if (!res.ok) {
    throw new Error("Failed to fetch backend health status");
  }
  return res.json() as Promise<{ status: string }>;
}

export default function Home() {
  const { data, status, refetch, isFetching } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    retry: 1,
    refetchInterval: 10000, // Refresh health every 10 seconds
  });

  return (
    <div className="relative min-h-screen w-full overflow-hidden bg-slate-950 text-slate-100 flex flex-col justify-between selection:bg-indigo-500 selection:text-white">
      {/* Background gradients */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(99,102,241,0.08),transparent_50%),radial-gradient(circle_at_bottom_left,rgba(168,85,247,0.05),transparent_50%)] pointer-events-none" />
      
      {/* Top Navbar */}
      <header className="border-b border-slate-900 bg-slate-950/80 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="relative flex items-center justify-center w-9 h-9 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 shadow-md shadow-indigo-500/20">
              <Brain className="w-5 h-5 text-white" />
            </div>
            <span className="font-semibold tracking-tight text-lg bg-clip-text text-transparent bg-gradient-to-r from-white via-slate-200 to-slate-400">
              Second Brain
            </span>
          </div>
          
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-900/50 border border-slate-800 text-xs font-medium">
              <span className="relative flex h-2 w-2">
                <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                  status === "success" && data?.status === "ok" ? "bg-emerald-400" : status === "pending" ? "bg-amber-400" : "bg-rose-400"
                }`}></span>
                <span className={`relative inline-flex rounded-full h-2 w-2 ${
                  status === "success" && data?.status === "ok" ? "bg-emerald-500" : status === "pending" ? "bg-amber-500" : "bg-rose-500"
                }`}></span>
              </span>
              <span className="text-slate-400">
                {status === "success" && data?.status === "ok" ? "Local Node Live" : status === "pending" ? "Connecting..." : "Node Offline"}
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex flex-col items-center justify-center max-w-4xl mx-auto px-6 py-20 w-full relative">
        <div className="text-center space-y-6 max-w-2xl mb-12">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-indigo-500/30 bg-indigo-500/5 text-indigo-400 text-xs font-medium tracking-wide uppercase mb-2 animate-fade-in">
            <Activity className="w-3.5 h-3.5" />
            Environnement Local Initialisé
          </div>
          
          <h1 className="text-4xl sm:text-5xl md:text-6xl font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white via-slate-100 to-slate-400 leading-tight">
            Cohérence <br className="sm:hidden" />
            <span className="bg-gradient-to-r from-indigo-400 via-purple-400 to-pink-400 bg-clip-text">
              Argumentative
            </span>
          </h1>
          
          <p className="text-slate-400 text-base sm:text-lg max-w-xl mx-auto leading-relaxed">
            Votre espace d'analyse sémantique et de structuration argumentative fonctionnant à 100% sur votre machine, sans aucune donnée externe.
          </p>
        </div>

        {/* Status Dashboard Card */}
        <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900/30 backdrop-blur-xl p-6 shadow-2xl relative overflow-hidden group hover:border-slate-700/50 transition-all duration-300">
          <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-indigo-500/20 to-transparent" />
          
          <div className="flex items-center justify-between border-b border-slate-800/60 pb-4 mb-4">
            <div className="flex items-center gap-2">
              <Server className="w-4.5 h-4.5 text-slate-400" />
              <h3 className="font-semibold text-sm text-slate-300">Statut des Services</h3>
            </div>
            {isFetching && <Loader2 className="w-4 h-4 text-indigo-400 animate-spin" />}
          </div>

          <div className="space-y-4">
            {/* Backend Service Row */}
            <div className="flex items-center justify-between p-3 rounded-lg bg-slate-950/40 border border-slate-900">
              <span className="text-sm font-medium text-slate-400">FastAPI Backend</span>
              <div className="flex items-center gap-2">
                {status === "success" && data?.status === "ok" ? (
                  <>
                    <span className="text-sm font-semibold text-emerald-400">backend: ok</span>
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  </>
                ) : status === "pending" ? (
                  <>
                    <span className="text-sm font-medium text-amber-400">Vérification...</span>
                    <Loader2 className="w-4 h-4 text-amber-400 animate-spin" />
                  </>
                ) : (
                  <>
                    <span className="text-sm font-semibold text-rose-400">backend: offline</span>
                    <XCircle className="w-4 h-4 text-rose-400" />
                  </>
                )}
              </div>
            </div>

            {/* Model Info Row */}
            <div className="p-3.5 rounded-lg bg-slate-950/40 border border-slate-900 space-y-2 text-xs">
              <div className="flex justify-between text-slate-400">
                <span>Docker Infrastructure :</span>
                <span className="text-slate-300 font-medium">Postgres + Ollama</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>Modèle de Chat :</span>
                <span className="text-indigo-400 font-medium">Qwen 2.5 7B</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>Modèle Embeddings :</span>
                <span className="text-purple-400 font-medium">Nomic Embed</span>
              </div>
            </div>
          </div>

          {/* Action button to retry */}
          <div className="mt-5">
            <Button 
              onClick={() => refetch()} 
              disabled={isFetching}
              className="w-full bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700/50 hover:border-slate-600 rounded-lg text-xs py-2 shadow-sm flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
            >
              Re-tester la connexion
            </Button>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-900 py-6 bg-slate-950 text-center text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-6">
          Second Brain Local Node • FastAPI + Next.js + Ollama • Cohérence Argumentative
        </div>
      </footer>
    </div>
  );
}
