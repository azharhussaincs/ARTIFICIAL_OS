"use client";
import { Activity, Command, Menu } from "lucide-react";
import { ui, useUI } from "../../store/uiStore";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";

interface Props { liveState: "idle" | "running" | "complete" | "error"; }

export function TopBar({ liveState }: Props) {
  const [healthy, setHealthy] = useState<boolean | null>(null);

  useEffect(() => {
    let alive = true;
    api.health().then(() => alive && setHealthy(true)).catch(() => alive && setHealthy(false));
    return () => { alive = false; };
  }, []);

  const dotClass =
    liveState === "running" ? "bg-accent animate-pulse" :
    liveState === "complete" ? "bg-signal" :
    liveState === "error"    ? "bg-danger" :
    healthy === false ? "bg-danger" : healthy ? "bg-signal" : "bg-muted";

  const stateLabel =
    liveState === "running" ? "scanning" :
    liveState === "complete" ? "ready" :
    liveState === "error"    ? "error" :
    healthy === false ? "api offline" : healthy ? "online" : "checking…";

  return (
    <header className="sticky top-0 z-20 glass-strong border-b border-white/5">
      <div className="px-5 md:px-8 h-14 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <button
            className="md:hidden btn-ghost !p-2"
            onClick={() => ui.set({ sidebarOpen: true })}
            aria-label="Open menu"
          >
            <Menu className="w-4 h-4" />
          </button>
          <div className="hidden md:flex items-center gap-2 text-xs font-mono text-slate-500">
            <Activity className="w-3.5 h-3.5 text-accent" />
            <span>cross-identity intelligence operations console</span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => ui.set({ cmdOpen: true })}
            className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-md
                       border border-white/5 hover:border-white/15
                       bg-white/[0.02] text-xs text-slate-400 hover:text-slate-200 transition"
          >
            <Command className="w-3.5 h-3.5" /> Quick command
            <kbd className="ml-2 px-1.5 py-0.5 rounded border border-white/10 text-[10px] font-mono">⌘ K</kbd>
          </button>

          <div className="flex items-center gap-2 px-3 py-1 rounded-full border border-white/5 bg-white/[0.03]">
            <span className={`w-2 h-2 rounded-full ${dotClass}`} />
            <span className="text-[11px] font-mono uppercase tracking-widest text-slate-400">{stateLabel}</span>
          </div>
        </div>
      </div>
    </header>
  );
}
