"use client";
import { motion } from "framer-motion";
import { useCounter } from "../../hooks/useCounter";
import { cn } from "../../lib/cn";

interface Props {
  label: string;
  value: number | string;
  hint?: string;
  icon?: React.ComponentType<{ className?: string }>;
  accent?: "default" | "signal" | "warn" | "danger" | "violet";
  delay?: number;
  pulse?: boolean;
}

const ACCENT: Record<NonNullable<Props["accent"]>, string> = {
  default: "text-accent",
  signal:  "text-signal",
  warn:    "text-warn",
  danger:  "text-danger",
  violet:  "text-accent2",
};

export function MetricCard({ label, value, hint, icon: Icon, accent = "default", delay = 0, pulse }: Props) {
  const isNumber = typeof value === "number";
  const animated = useCounter(isNumber ? (value as number) : 0);
  const display = isNumber ? Math.round(animated).toString() : String(value);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay, ease: [0.16, 1, 0.3, 1] }}
      whileHover={{ y: -2 }}
      className="glass rounded-xl p-4 relative overflow-hidden neon-border"
    >
      <div className="flex items-center justify-between">
        <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-slate-500">
          {label}
        </div>
        {Icon && <Icon className={cn("w-3.5 h-3.5", ACCENT[accent])} />}
      </div>
      <div className={cn("mt-2 font-mono text-2xl md:text-3xl font-bold leading-none", ACCENT[accent])}>
        {display}
      </div>
      {hint && <div className="mt-1 text-[11px] text-slate-500">{hint}</div>}
    </motion.div>
  );
}
