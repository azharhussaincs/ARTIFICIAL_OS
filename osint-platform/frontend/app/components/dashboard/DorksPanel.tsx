"use client";
import { motion } from "framer-motion";
import { Copy, ExternalLink } from "lucide-react";
import { useState } from "react";
import type { Dork } from "../../lib/types";
import { GlassCard, CardHeader } from "../ui/GlassCard";

export function DorksPanel({ dorks }: { dorks: Dork[] }) {
  const [copied, setCopied] = useState<number | null>(null);
  return (
    <GlassCard className="h-full">
      <CardHeader title="Generated Dorks" hint={`${dorks.length} queries`} />
      <div className="space-y-1 max-h-96 overflow-y-auto pr-1">
        {dorks.map((d, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2, delay: Math.min(i, 12) * 0.02 }}
            className="px-2 py-2 rounded-md hover:bg-white/[0.04] transition group"
          >
            <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-slate-500">{d.label}</div>
            <div className="font-mono text-[12px] text-slate-200 break-all leading-snug mt-0.5">{d.query}</div>
            <div className="mt-1 flex flex-wrap gap-1.5 opacity-70 group-hover:opacity-100 transition">
              <a className="btn-ghost" href={d.google}     target="_blank" rel="noopener"><ExternalLink className="w-3 h-3" /> google</a>
              <a className="btn-ghost" href={d.bing}       target="_blank" rel="noopener"><ExternalLink className="w-3 h-3" /> bing</a>
              <a className="btn-ghost" href={d.duckduckgo} target="_blank" rel="noopener"><ExternalLink className="w-3 h-3" /> ddg</a>
              <button
                className="btn-ghost"
                onClick={() => { navigator.clipboard.writeText(d.query); setCopied(i); setTimeout(() => setCopied(null), 1400); }}
              >
                <Copy className="w-3 h-3" /> {copied === i ? "copied" : "copy"}
              </button>
            </div>
          </motion.div>
        ))}
        {!dorks.length && <div className="text-sm text-slate-600 font-mono">// no dorks generated</div>}
      </div>
    </GlassCard>
  );
}
