"use client";
import { motion } from "framer-motion";
import { ShieldCheck, Database, Calendar, Mail, Phone, User, Tag, Hash } from "lucide-react";
import { GlassCard, CardHeader } from "../ui/GlassCard";
import type { LocalDatabaseBlock } from "../../lib/types";

interface Props {
  block?: LocalDatabaseBlock;
}

// Authoritative VERIFIED LOCAL DATABASE (100% TRUST) panel.
// Renders ES tc_index hits as the FIRST section on the page. Always
// rendered when a search has run — when there are no records it shows the
// spec'd "❌ No data found in local database" message rather than being
// hidden, so analysts can never confuse "no DB section" with "DB skipped".
export function LocalDatabasePanel({ block }: Props) {
  if (!block) return null;
  const { records = [], found, count } = block;

  return (
    <GlassCard padding={false} className="border-emerald-500/30">
      <div className="px-5 pt-5">
        <CardHeader
          title="VERIFIED LOCAL DATABASE"
          hint="100% trust · authoritative"
          action={
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1 text-[10px] font-mono uppercase tracking-[0.18em] text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 rounded-md px-2 py-1">
                <ShieldCheck className="w-3 h-3" />
                {found ? "VERIFIED" : "NO MATCH"}
              </span>
              <span className="text-[11px] font-mono text-slate-400">
                {count} record{count === 1 ? "" : "s"}
              </span>
            </div>
          }
        />
      </div>

      <div className="px-5 pb-5">
        {!found || records.length === 0 ? (
          <div className="rounded-xl border border-rose-500/20 bg-rose-500/5 p-4 text-rose-200/80 font-mono text-sm">
            ❌ No data found in local database
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3">
            {records.map((r, i) => {
              const tagsArr = Array.isArray(r.TAGS)
                ? r.TAGS
                : (r.TAGS || "").split(",").map(t => t.trim()).filter(Boolean);
              return (
              <motion.div
                key={r.es_id || `${r.NAME}-${i}`}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25, delay: i * 0.04 }}
                className="rounded-xl border border-emerald-500/30 bg-gradient-to-br from-emerald-500/[0.06] to-transparent p-4"
              >
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="flex items-center gap-2 text-emerald-300/90">
                    <Database className="w-4 h-4" />
                    <span className="font-display font-semibold text-slate-100">
                      {r.NAME || "—"}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-[10px] font-mono">
                    <span className="text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 rounded px-1.5 py-0.5">
                      Confidence: 100
                    </span>
                    <span className="text-slate-400 bg-white/5 border border-white/10 rounded px-1.5 py-0.5">
                      Source: Local DB
                    </span>
                  </div>
                </div>

                <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2 text-sm font-mono">
                  <Row icon={<User className="w-3.5 h-3.5 text-slate-400" />} label="Name"  value={r.NAME} />
                  <Row icon={<Phone className="w-3.5 h-3.5 text-slate-400" />} label="Phone" value={r.PHONE} />
                  <Row icon={<Mail className="w-3.5 h-3.5 text-slate-400" />}  label="Email" value={r.EMAIL} />
                  <Row icon={<Tag className="w-3.5 h-3.5 text-slate-400" />}   label="Tags"
                       value={tagsArr.length ? tagsArr.join(", ") : ""} />
                  <Row icon={<Calendar className="w-3.5 h-3.5 text-slate-400" />} label="Date"
                       value={r.ASONDATE} />
                  <Row icon={<Hash className="w-3.5 h-3.5 text-slate-400" />}     label="Matched"
                       value={r.matched_field
                         ? `${r.matched_field}${r.match_reason ? ` (${r.match_reason})` : ""}`
                         : ""} />
                </dl>
              </motion.div>
              );
            })}
          </div>
        )}
      </div>
    </GlassCard>
  );
}

function Row({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-center gap-2 min-w-0">
      <span className="text-[10px] uppercase tracking-[0.14em] text-slate-500 w-14 shrink-0 inline-flex items-center gap-1.5">
        {icon}{label}
      </span>
      <span className="text-slate-200 truncate" title={value || ""}>
        {value || "—"}
      </span>
    </div>
  );
}
