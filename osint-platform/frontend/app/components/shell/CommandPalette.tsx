"use client";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Crosshair, History, ListChecks, Network, Terminal } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { ui, useUI } from "../../store/uiStore";
import { useKeyboard } from "../../hooks/useKeyboard";
import type { QueryKind } from "../../lib/types";

interface Action {
  id: string;
  label: string;
  hint: string;
  icon: React.ComponentType<{ className?: string }>;
  run: () => void;
}

export function CommandPalette() {
  const open = useUI((s) => s.cmdOpen);
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useKeyboard({ key: "k", meta: true }, () => ui.set({ cmdOpen: !ui.get().cmdOpen }), true);
  useKeyboard({ key: "Escape" }, () => ui.set({ cmdOpen: false }), true);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 30);
  }, [open]);

  const close = () => { ui.set({ cmdOpen: false }); setQuery(""); };
  const goAndClose = (anchor: string) => () => { close(); document.querySelector(anchor)?.scrollIntoView({ behavior: "smooth" }); };
  const setKindAndFocus = (kind: QueryKind) => () => {
    close();
    ui.set({ kind });
    setTimeout(() => document.getElementById("query-input")?.focus(), 100);
  };

  const actions: Action[] = useMemo(() => [
    { id: "go-search",   label: "Go: Search",        hint: "scroll to search",   icon: Crosshair,  run: goAndClose("#search") },
    { id: "go-findings", label: "Go: Findings",      hint: "scroll to findings", icon: ListChecks, run: goAndClose("#findings") },
    { id: "go-graph",    label: "Go: Identity Graph",hint: "scroll to graph",    icon: Network,    run: goAndClose("#graph") },
    { id: "go-stream",   label: "Go: Live stream",   hint: "scroll to terminal", icon: Terminal,   run: goAndClose("#stream") },
    { id: "go-history",  label: "Go: History",       hint: "scroll to history",  icon: History,    run: goAndClose("#history") },
    { id: "kind-name",   label: "Search by Name",     hint: "kind=name",     icon: Crosshair, run: setKindAndFocus("name") },
    { id: "kind-email",  label: "Search by Email",    hint: "kind=email",    icon: Crosshair, run: setKindAndFocus("email") },
    { id: "kind-phone",  label: "Search by Phone",    hint: "kind=phone",    icon: Crosshair, run: setKindAndFocus("phone") },
    { id: "kind-user",   label: "Search by Username", hint: "kind=username", icon: Crosshair, run: setKindAndFocus("username") },
  ], []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return actions;
    return actions.filter((a) => a.label.toLowerCase().includes(q) || a.hint.toLowerCase().includes(q));
  }, [actions, query]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-start justify-center pt-[14vh] px-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <div className="absolute inset-0 bg-ink/80 backdrop-blur-md" onClick={close} aria-hidden />
          <motion.div
            initial={{ y: -20, opacity: 0, scale: 0.97 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: -20, opacity: 0, scale: 0.97 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="relative w-full max-w-xl glass-strong rounded-2xl neon-border overflow-hidden"
          >
            <div className="flex items-center gap-3 px-4 py-3 border-b border-white/5">
              <Crosshair className="w-4 h-4 text-accent" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Type a command…"
                className="flex-1 bg-transparent outline-none text-sm placeholder:text-slate-600 font-mono"
              />
              <kbd className="px-1.5 py-0.5 rounded border border-white/10 text-[10px] font-mono text-slate-500">ESC</kbd>
            </div>
            <div className="max-h-[50vh] overflow-y-auto py-2">
              {filtered.map((a) => {
                const Icon = a.icon;
                return (
                  <button
                    key={a.id}
                    onClick={a.run}
                    className="w-full px-4 py-2.5 flex items-center gap-3 text-left hover:bg-white/[0.04] transition group"
                  >
                    <Icon className="w-4 h-4 text-slate-500 group-hover:text-accent" />
                    <div className="flex-1">
                      <div className="text-sm text-slate-100">{a.label}</div>
                      <div className="text-[11px] font-mono text-slate-500">{a.hint}</div>
                    </div>
                    <ArrowRight className="w-3.5 h-3.5 text-slate-600 group-hover:text-accent" />
                  </button>
                );
              })}
              {!filtered.length && (
                <div className="px-4 py-6 text-sm text-slate-500 text-center">no commands match</div>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
