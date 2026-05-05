"use client";
import { motion } from "framer-motion";
import type { WhoisRecord } from "../../lib/types";
import { GlassCard, CardHeader } from "../ui/GlassCard";

export function WhoisPanel({ records }: { records: WhoisRecord[] }) {
  return (
    <GlassCard className="h-full">
      <CardHeader title="WHOIS / RDAP" hint={`${records.length} domains`} />
      <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
        {records.map((w, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25, delay: Math.min(i, 8) * 0.04 }}
            className="rounded-lg border border-white/5 bg-white/[0.02] p-3 text-[11px] font-mono"
          >
            <div className="flex justify-between items-baseline gap-2">
              <div className="text-accent">{w.domain}</div>
              <div className="text-slate-500 truncate text-right">{w.registrar || "—"}</div>
            </div>
            <div className="text-slate-400 mt-1">created: {w.created || "—"} · expires: {w.expires || "—"}</div>
            {w.nameservers.length > 0 && (
              <div className="text-slate-500 mt-1 truncate">ns: {w.nameservers.join(", ")}</div>
            )}
            {w.contacts.length > 0 && (
              <div className="mt-2 space-y-1">
                {w.contacts.map((c, j) => (
                  <div key={j} className="text-slate-300">
                    <span className="text-accent2">{c.roles || "contact"}</span>: {c.name || ""} {c.email ? `· ${c.email}` : ""} {c.phone ? `· ${c.phone}` : ""}
                  </div>
                ))}
              </div>
            )}
            {w.error && <div className="text-danger mt-1">{w.error}</div>}
          </motion.div>
        ))}
        {!records.length && <div className="text-sm text-slate-600 font-mono">// no domains looked up</div>}
      </div>
    </GlassCard>
  );
}
