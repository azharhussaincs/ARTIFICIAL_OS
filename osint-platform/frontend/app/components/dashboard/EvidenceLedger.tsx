"use client";
import { motion } from "framer-motion";
import { ScrollText } from "lucide-react";
import { useMemo, useState } from "react";
import type { EvidenceRow } from "../../lib/types";
import { GlassCard, CardHeader } from "../ui/GlassCard";
import { cn } from "../../lib/cn";
import { tsShort } from "../../lib/format";

/**
 * Chronological audit trail: every signal across every Finding, with
 * delta, reason, and source URL. This is the single view an analyst
 * uses to understand "WHY did the engine reach these conclusions?"
 *
 * Filters: by sign (positive/negative deltas), by signal kind, by Finding type.
 */
export function EvidenceLedger({ rows }: { rows: EvidenceRow[] }) {
  const [signFilter, setSignFilter] = useState<"all" | "positive" | "negative">("all");
  const [typeFilter, setTypeFilter] = useState<string>("");

  const types = useMemo(
    () => Array.from(new Set(rows.map((r) => r.type))).sort(),
    [rows],
  );

  const filtered = useMemo(() => {
    return rows.filter((r) => {
      if (signFilter === "positive" && r.delta <= 0) return false;
      if (signFilter === "negative" && r.delta > 0) return false;
      if (typeFilter && r.type !== typeFilter) return false;
      return true;
    });
  }, [rows, signFilter, typeFilter]);

  if (!rows.length) return null;

  return (
    <GlassCard padding={false} id="evidence">
      <div className="px-5 pt-5">
        <CardHeader
          title="Evidence Ledger"
          hint={`${rows.length} signals · chronological audit trail`}
          action={
            <div className="flex flex-wrap gap-2">
              <select
                value={signFilter}
                onChange={(e) => setSignFilter(e.target.value as typeof signFilter)}
                className="bg-white/[0.04] border border-white/5 rounded-md text-[11px] font-mono text-slate-300 px-2 py-1 outline-none"
              >
                <option value="all">all signals</option>
                <option value="positive">positive only (+)</option>
                <option value="negative">negative only (−)</option>
              </select>
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className="bg-white/[0.04] border border-white/5 rounded-md text-[11px] font-mono text-slate-300 px-2 py-1 outline-none"
              >
                <option value="">all types</option>
                {types.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              <span className="inline-flex items-center gap-1 text-[10px] font-mono text-slate-500">
                <ScrollText className="w-3 h-3 text-accent2" /> source-backed
              </span>
            </div>
          }
        />
      </div>
      <div className="px-5 pb-5 max-h-[26rem] overflow-y-auto">
        <table className="w-full text-[11px] font-mono">
          <thead>
            <tr className="text-[10px] uppercase tracking-[0.16em] text-slate-500 border-b border-white/5">
              <th className="text-left py-1.5 pr-3">time</th>
              <th className="text-left py-1.5 pr-3">type</th>
              <th className="text-left py-1.5 pr-3">value</th>
              <th className="text-left py-1.5 pr-3">signal</th>
              <th className="text-right py-1.5 pr-3">Δ</th>
              <th className="text-left py-1.5 pr-3">reason</th>
              <th className="text-left py-1.5">source</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r, i) => (
              <motion.tr
                key={`${r.finding_key}-${r.signal}-${i}`}
                initial={{ opacity: 0, x: -3 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.18, delay: Math.min(i, 16) * 0.012 }}
                className="border-b border-white/[0.03] hover:bg-white/[0.03] transition"
              >
                <td className="py-1.5 pr-3 text-slate-600 whitespace-nowrap">{tsShort(r.at)}</td>
                <td className="py-1.5 pr-3 text-accent uppercase tracking-wider text-[10px]">{r.type}</td>
                <td className="py-1.5 pr-3 text-slate-200 max-w-[14rem] truncate" title={r.value}>{r.value}</td>
                <td className="py-1.5 pr-3 text-accent2">{r.signal}</td>
                <td
                  className={cn(
                    "py-1.5 pr-3 text-right font-bold",
                    r.delta >= 0 ? "text-signal" : "text-danger",
                  )}
                >
                  {r.delta >= 0 ? "+" : "−"}{Math.abs(r.delta)}
                </td>
                <td className="py-1.5 pr-3 text-slate-300 max-w-[24rem] truncate" title={r.reason}>{r.reason}</td>
                <td className="py-1.5 max-w-[14rem] truncate">
                  {r.source_url && !r.source_url.startsWith("urn:") ? (
                    <a href={r.source_url} target="_blank" rel="noopener" className="text-accent hover:underline">
                      {shortHost(r.source_url)}
                    </a>
                  ) : (
                    <span className="text-slate-600">{r.source_url || "—"}</span>
                  )}
                </td>
              </motion.tr>
            ))}
            {!filtered.length && (
              <tr>
                <td colSpan={7} className="py-6 text-center text-slate-500 text-sm">
                  // no signals match the current filters
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </GlassCard>
  );
}

function shortHost(url: string): string {
  try { return new URL(url).host.replace(/^www\./, ""); }
  catch { return url; }
}
