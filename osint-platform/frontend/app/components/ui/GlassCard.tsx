"use client";
import { motion, type HTMLMotionProps } from "framer-motion";
import { cn } from "../../lib/cn";

type Props = HTMLMotionProps<"div"> & {
  glow?: boolean;
  padding?: boolean;
};

export function GlassCard({ className, glow = true, padding = true, children, ...rest }: Props) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
      className={cn(
        "glass rounded-2xl relative overflow-hidden",
        glow && "neon-border",
        padding && "p-5",
        className,
      )}
      {...rest}
    >
      {children}
    </motion.div>
  );
}

export function CardHeader({ title, hint, action }: { title: string; hint?: string; action?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 mb-3">
      <div>
        <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-slate-500">{hint}</div>
        <div className="font-display font-semibold text-slate-100 text-sm tracking-wide">{title}</div>
      </div>
      {action}
    </div>
  );
}
