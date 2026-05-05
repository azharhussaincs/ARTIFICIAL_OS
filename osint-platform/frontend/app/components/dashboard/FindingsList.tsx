"use client";
import { motion, AnimatePresence } from "framer-motion";
import { Filter, ShieldCheck, FileText, FileDown } from "lucide-react";
import { useMemo } from "react";
import type { Finding, ProfileSnapshot } from "../../lib/types";
import { GlassCard, CardHeader } from "../ui/GlassCard";
import { FindingCard } from "./FindingCard";
import { ui, useUI } from "../../store/uiStore";
import { api } from "../../lib/api";

interface Props {
  findings: Finding[];
  snapshots?: ProfileSnapshot[];
  recordId?: number;
}

export function FindingsList({ findings, snapshots = [], recordId }: Props) {
  const filterType = useUI((s) => s.filterType);
  const minConf    = useUI((s) => s.filterMinConf);
  const verified   = useUI((s) => s.filterVerifiedOnly);
  const showSig    = useUI((s) => s.showSignals);

  const filtered = useMemo(() => {
    return findings.filter((f) => {
      if (filterType && f.type !== filterType) return false;
      if (f.confidence < minConf) return false;
      if (verified && !f.verified) return false;
      return true;
    });
  }, [findings, filterType, minConf, verified]);

  return (
    <GlassCard padding={false} id="findings">
      <div className="px-5 pt-5">
        <CardHeader
          title="Verified Findings"
          hint="cross-identity correlation"
          action={
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={filterType}
                onChange={(e) => ui.set({ filterType: e.target.value as typeof filterType })}
                className="bg-white/[0.04] border border-white/5 rounded-md text-[11px] font-mono text-slate-300 px-2 py-1 outline-none"
              >
                <option value="">all types</option>
                <option value="username">username</option>
                <option value="email">email</option>
                <option value="phone">phone</option>
                <option value="name">name</option>
                <option value="social_profile">social_profile</option>
                <option value="website">website</option>
                <option value="domain">domain</option>
              </select>
              <select
                value={minConf}
                onChange={(e) => ui.set({ filterMinConf: parseInt(e.target.value, 10) })}
                className="bg-white/[0.04] border border-white/5 rounded-md text-[11px] font-mono text-slate-300 px-2 py-1 outline-none"
              >
                <option value={50}>≥ 50 (possible+)</option>
                <option value={0}>any confidence</option>
                <option value={70}>≥ 70 (likely+)</option>
                <option value={90}>≥ 90 (high)</option>
              </select>
              <label className="flex items-center gap-1 text-[11px] text-slate-400 cursor-pointer">
                <input type="checkbox" checked={verified} onChange={(e) => ui.set({ filterVerifiedOnly: e.target.checked })} className="accent-accent" />
                <ShieldCheck className="w-3 h-3" /> verified only
              </label>
              <label className="flex items-center gap-1 text-[11px] text-slate-400 cursor-pointer">
                <input type="checkbox" checked={showSig} onChange={(e) => ui.set({ showSignals: e.target.checked })} className="accent-accent" />
                <Filter className="w-3 h-3" /> signal trail
              </label>
              <button
                disabled={!recordId}
                onClick={() => recordId && window.open(api.exportCsvUrl(recordId), "_blank")}
                className="btn-ghost"
              >
                <FileText className="w-3 h-3" /> CSV
              </button>
              <button
                disabled={!recordId}
                onClick={() => recordId && window.open(api.exportPdfUrl(recordId), "_blank")}
                className="btn-ghost"
              >
                <FileDown className="w-3 h-3" /> PDF
              </button>
            </div>
          }
        />
      </div>
      <div className="px-5 pb-5 grid grid-cols-1 lg:grid-cols-2 gap-3">
        <AnimatePresence mode="popLayout">
          {filtered.map((f, i) => (
            <FindingCard key={f.key} f={f} snapshots={snapshots} showSignals={showSig} index={i} />
          ))}
        </AnimatePresence>
        {!filtered.length && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="lg:col-span-2 text-sm text-slate-500 py-8 text-center font-mono"
          >
            // no findings match the current filters
          </motion.div>
        )}
      </div>
    </GlassCard>
  );
}
