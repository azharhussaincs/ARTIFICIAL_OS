"use client";
import { motion } from "framer-motion";
import { useCounter } from "../../hooks/useCounter";

interface Props {
  value: number;          // 0..100
  label: string;          // tier label
  size?: number;
}

export function ConfidenceRing({ value, label, size = 168 }: Props) {
  const v = useCounter(value, 900);
  const pct = Math.max(0, Math.min(100, v));
  const stroke = 12;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const dash = (pct / 100) * c;

  const tone = pct >= 90 ? "#34d399"
            : pct >= 70 ? "#22d3ee"
            : pct >= 50 ? "#fbbf24"
            : pct >= 25 ? "#fb923c"
                        : "#64748b";

  return (
    <div className="relative grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="rotate-[-90deg]">
        <defs>
          <linearGradient id="ringGrad" x1="0" x2="1" y1="0" y2="1">
            <stop offset="0%"  stopColor="#22d3ee" />
            <stop offset="100%" stopColor="#a78bfa" />
          </linearGradient>
        </defs>
        <circle
          cx={size / 2} cy={size / 2} r={r}
          fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth={stroke}
        />
        <motion.circle
          cx={size / 2} cy={size / 2} r={r}
          fill="none"
          stroke="url(#ringGrad)"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${c - dash}`}
          style={{ filter: `drop-shadow(0 0 14px ${tone})` }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center">
        <div className="text-center">
          <div className="font-mono text-4xl font-bold" style={{ color: tone }}>
            {Math.round(pct)}
          </div>
          <div className="text-[10px] font-mono uppercase tracking-[0.22em] text-slate-500 mt-1">
            {label}
          </div>
        </div>
      </div>
    </div>
  );
}
