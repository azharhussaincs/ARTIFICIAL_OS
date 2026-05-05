"use client";
import { motion } from "framer-motion";
import {
  Crosshair, Network, ListChecks, History, Terminal, Settings, ShieldCheck,
} from "lucide-react";
import { cn } from "../../lib/cn";
import { useUI, ui } from "../../store/uiStore";

const NAV = [
  { id: "search",   label: "Search",   icon: Crosshair, anchor: "#search" },
  { id: "findings", label: "Findings", icon: ListChecks, anchor: "#findings" },
  { id: "graph",    label: "Graph",    icon: Network,    anchor: "#graph" },
  { id: "stream",   label: "Live",     icon: Terminal,   anchor: "#stream" },
  { id: "history",  label: "History",  icon: History,    anchor: "#history" },
  { id: "api",      label: "API",      icon: Settings,   anchor: "/docs", external: true },
];

export function Sidebar() {
  const open = useUI((s) => s.sidebarOpen);

  return (
    <>
      {/* Mobile overlay */}
      <div
        className={cn(
          "fixed inset-0 bg-ink/70 backdrop-blur-sm z-30 transition-opacity md:hidden",
          open ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none",
        )}
        onClick={() => ui.set({ sidebarOpen: false })}
        aria-hidden
      />

      <aside
        className={cn(
          "fixed md:sticky top-0 left-0 h-screen w-64 z-40 md:z-10",
          "transform transition-transform duration-300 ease-out",
          open ? "translate-x-0" : "-translate-x-full md:translate-x-0",
        )}
      >
        <div className="h-full glass-strong border-r border-white/5 flex flex-col">
          {/* Logo */}
          <div className="p-5 border-b border-white/5">
            <div className="flex items-center gap-3">
              <motion.div
                initial={{ rotate: -45, opacity: 0 }}
                animate={{ rotate: 0, opacity: 1 }}
                transition={{ duration: 0.4 }}
                className="w-10 h-10 rounded-xl bg-gradient-to-br from-accent to-accent2 grid place-items-center font-mono font-extrabold text-ink shadow-glow"
              >
                O
              </motion.div>
              <div>
                <div className="font-display font-semibold tracking-wide text-slate-100 leading-none">
                  OSINT://platform
                </div>
                <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-500 mt-1">
                  intel · v1.2
                </div>
              </div>
            </div>
          </div>

          {/* Nav */}
          <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto no-scrollbar">
            {NAV.map((item, i) => {
              const Icon = item.icon;
              return (
                <motion.a
                  key={item.id}
                  href={item.anchor}
                  target={item.external ? "_blank" : undefined}
                  rel={item.external ? "noopener" : undefined}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.05 * i, duration: 0.3 }}
                  whileHover={{ x: 2 }}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2.5 rounded-lg",
                    "text-sm text-slate-400 hover:text-slate-100",
                    "hover:bg-white/[0.04] transition-colors group",
                  )}
                  onClick={() => ui.set({ sidebarOpen: false })}
                >
                  <Icon className="w-4 h-4 group-hover:text-accent transition-colors" />
                  <span className="font-medium">{item.label}</span>
                </motion.a>
              );
            })}
          </nav>

          {/* Ethics footer */}
          <div className="p-4 mx-3 mb-4 rounded-xl border border-white/5 bg-white/[0.02]">
            <div className="flex items-center gap-2 mb-1">
              <ShieldCheck className="w-3.5 h-3.5 text-signal" />
              <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-slate-400">
                public-source only
              </div>
            </div>
            <p className="text-[11px] text-slate-500 leading-snug">
              Respects robots.txt · no auth bypass · per-IP rate limited
            </p>
          </div>
        </div>
      </aside>
    </>
  );
}
