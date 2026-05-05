"use client";
import { motion } from "framer-motion";
import { useEffect, useState, useCallback } from "react";
import type { HistoryItem, SearchResponse } from "../../lib/types";
import { api } from "../../lib/api";
import { GlassCard, CardHeader } from "../ui/GlassCard";
import { confClass } from "../../lib/format";
import { cn } from "../../lib/cn";

export function HistoryPanel({ onPick, refreshKey }: { onPick: (r: SearchResponse) => void; refreshKey?: number }) {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.history(12, 0);
      setItems(res.items);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { reload(); }, [reload, refreshKey]);

  return (
    <GlassCard padding={false} id="history">
      <div className="px-5 pt-5">
        <CardHeader
          title="Recent Searches"
          hint={`${items.length} records`}
          action={<button onClick={reload} className="btn-ghost">refresh</button>}
        />
      </div>
      <div className="px-5 pb-5 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {loading && <div className="md:col-span-2 lg:col-span-3 text-sm text-slate-600 font-mono">// loading…</div>}
        {!loading && !items.length && (
          <div className="md:col-span-2 lg:col-span-3 text-sm text-slate-600 font-mono">// no prior searches yet</div>
        )}
        {items.map((it, i) => (
          <motion.button
            key={it.id}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25, delay: Math.min(i, 8) * 0.03 }}
            whileHover={{ y: -2 }}
            onClick={async () => {
              try {
                const data = await api.historyOne(it.id);
                (data as SearchResponse).id = it.id;
                onPick(data);
              } catch { /* ignore */ }
            }}
            className="text-left rounded-xl border border-white/5 bg-white/[0.02] hover:bg-white/[0.04] p-3 transition"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-slate-500">{it.query_kind}</div>
                <div className="font-display font-medium text-slate-100 truncate">{it.query_value}</div>
              </div>
              <span className={cn("conf-pill", confClass(it.confidence_label))}>{it.confidence}</span>
            </div>
            <div className="text-[11px] font-mono text-slate-500 mt-2">
              {new Date(it.created_at).toLocaleString()}
            </div>
          </motion.button>
        ))}
      </div>
    </GlassCard>
  );
}
