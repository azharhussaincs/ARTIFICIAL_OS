"use client";
import { motion, AnimatePresence } from "framer-motion";
import { AtSign, ChevronDown, Hash, Phone, Users, User, Zap } from "lucide-react";
import { useState } from "react";
import { NeonButton } from "../ui/NeonButton";
import { ScannerOverlay } from "../ui/ScannerOverlay";
import type { SearchBundleInput } from "../../lib/types";

const FIELDS: Array<{
  id: keyof SearchBundleInput;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  ph: string;
}> = [
  { id: "name",     label: "Full name",  icon: User,   ph: "e.g. Jane Doe" },
  { id: "username", label: "Username",   icon: Hash,   ph: "e.g. janedoe" },
  { id: "email",    label: "Email",      icon: AtSign, ph: "e.g. jane.doe@example.com" },
  { id: "phone",    label: "Phone",      icon: Phone,  ph: "e.g. +1 415 555 1212" },
];

export function MultiInputForm({
  open, onToggle, running, onRun,
}: {
  open: boolean;
  onToggle: () => void;
  running: boolean;
  onRun: (bundle: SearchBundleInput) => void;
}) {
  const [bundle, setBundle] = useState<SearchBundleInput>({});

  function set(k: keyof SearchBundleInput, v: string) {
    setBundle((b) => ({ ...b, [k]: v }));
  }
  function submit() {
    const cleaned: SearchBundleInput = {};
    for (const k of Object.keys(bundle) as Array<keyof SearchBundleInput>) {
      const v = (bundle[k] || "").trim();
      if (v) cleaned[k] = v;
    }
    if (!Object.keys(cleaned).length || running) return;
    onRun(cleaned);
  }

  const filled = Object.values(bundle).filter((v) => v && v.trim()).length;

  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={onToggle}
        className="flex items-center gap-2 text-xs font-mono uppercase tracking-[0.16em] text-slate-500 hover:text-accent transition"
      >
        <Users className="w-3.5 h-3.5" />
        Multi-input identity bundle
        <ChevronDown className={`w-3 h-3 transition-transform ${open ? "rotate-180" : ""}`} />
        {filled > 0 && <span className="px-1.5 py-0.5 rounded border border-accent/40 text-[10px] text-accent">{filled} filled</span>}
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25 }}
            className="overflow-hidden"
          >
            <div className="mt-3 rounded-xl border border-white/5 bg-ink/40 p-4 relative">
              <ScannerOverlay active={running} />
              <div className="text-[11px] text-slate-500 mb-3">
                Provide any combination — the engine seeds all of them, cross-links them, and runs identity correlation across the union.
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {FIELDS.map(({ id, label, icon: Icon, ph }) => (
                  <label key={id} className="flex flex-col gap-1">
                    <span className="text-[10px] font-mono uppercase tracking-[0.16em] text-slate-500 flex items-center gap-1.5">
                      <Icon className="w-3 h-3 text-accent" />
                      {label}
                    </span>
                    <input
                      value={bundle[id] || ""}
                      onChange={(e) => set(id, e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && submit()}
                      placeholder={ph}
                      className="bg-ink/70 border border-white/5 focus:border-accent/60 rounded-lg px-3 py-2
                                 font-mono text-sm placeholder:text-slate-600 outline-none transition-colors"
                    />
                  </label>
                ))}
              </div>
              <div className="mt-4 flex items-center justify-between">
                <div className="text-[11px] text-slate-500">
                  Bundles cross-link every seed and produce one merged identity graph.
                </div>
                <NeonButton onClick={submit} disabled={running || !filled} loading={running}>
                  <Zap className="w-4 h-4" />
                  {running ? "Resolving…" : `Resolve identity (${filled})`}
                </NeonButton>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
