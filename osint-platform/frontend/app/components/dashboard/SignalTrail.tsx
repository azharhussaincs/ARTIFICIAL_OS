"use client";
import { motion } from "framer-motion";
import type { Signal } from "../../lib/types";
import { cn } from "../../lib/cn";

export function SignalTrail({ signals, total }: { signals: Signal[]; total: number }) {
  if (!signals.length) return null;
  return (
    <div className="border-t border-white/5 pt-2 space-y-1">
      {signals.map((s, i) => {
        const pos = s.delta >= 0;
        return (
          <motion.div
            key={`${s.kind}-${i}`}
            initial={{ opacity: 0, x: -4 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.2, delay: i * 0.03 }}
            className="flex items-baseline gap-2 text-[11px] font-mono leading-tight"
          >
            <span
              className={cn(
                "w-9 text-right rounded px-1 py-[1px] font-bold tabular-nums",
                pos ? "text-signal bg-signal/10" : "text-danger bg-danger/10",
              )}
            >
              {pos ? "+" : "−"}
              {Math.abs(s.delta)}
            </span>
            <span className="text-accent2 min-w-[7.5rem] truncate">{s.kind}</span>
            <span className="text-slate-300 flex-1">{s.reason}</span>
          </motion.div>
        );
      })}
      <div className="text-right text-[10px] font-mono text-slate-600 pt-1">
        Σ = {total} → clamp(0,100)
      </div>
    </div>
  );
}
