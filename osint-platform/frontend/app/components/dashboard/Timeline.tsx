"use client";
import { motion } from "framer-motion";
import type { TimelineEntry } from "../../lib/types";
import { GlassCard, CardHeader } from "../ui/GlassCard";
import { tsShort } from "../../lib/format";

export function Timeline({ entries }: { entries: TimelineEntry[] }) {
  return (
    <GlassCard className="h-full">
      <CardHeader title="Engine Timeline" hint="passes" />
      <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
        {entries.map((t, i) => (
          <motion.div
            key={`${t.timestamp}-${i}`}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.25, delay: Math.min(i, 12) * 0.02 }}
            className="grid grid-cols-[60px_90px_1fr] items-baseline gap-2 text-[11px] font-mono"
          >
            <span className="text-slate-600">{tsShort(t.timestamp)}</span>
            <span className="text-accent2 uppercase tracking-widest">{t.stage}</span>
            <span className="text-slate-300">{t.detail}</span>
          </motion.div>
        ))}
        {!entries.length && <div className="text-sm text-slate-600 font-mono">// awaiting input…</div>}
      </div>
    </GlassCard>
  );
}
