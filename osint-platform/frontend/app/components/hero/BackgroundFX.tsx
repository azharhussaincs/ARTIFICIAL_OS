"use client";
import { motion } from "framer-motion";
import { useMemo } from "react";

/** Animated cyber-style background: grid + drifting orbs + particles. */
export function BackgroundFX() {
  // Deterministic particles (avoids hydration mismatch).
  const particles = useMemo(
    () => Array.from({ length: 28 }).map((_, i) => ({
      id: i,
      x: ((i * 137) % 100) + Math.sin(i) * 4,
      y: ((i * 53)  % 100) + Math.cos(i) * 4,
      delay: (i % 10) * 0.4,
      dur: 4 + (i % 5),
      size: 1 + (i % 3),
    })),
    [],
  );

  return (
    <div className="absolute inset-0 -z-10 overflow-hidden pointer-events-none">
      <div className="absolute inset-0 bg-grid" />
      <div className="absolute inset-0 bg-radial-fade" />

      {/* Drifting orbs */}
      <div className="bg-orb w-[420px] h-[420px] left-[8%] top-[-100px] bg-accent/20 animate-drift" />
      <div className="bg-orb w-[520px] h-[520px] right-[5%] top-[20%] bg-accent2/20 animate-drift" style={{ animationDelay: "-6s" }} />
      <div className="bg-orb w-[380px] h-[380px] left-[35%] bottom-[-180px] bg-signal/10 animate-drift" style={{ animationDelay: "-12s" }} />

      {/* Particle layer */}
      {particles.map((p) => (
        <motion.span
          key={p.id}
          className="absolute rounded-full bg-accent/60"
          style={{
            left: `${p.x}%`,
            top:  `${p.y}%`,
            width:  p.size,
            height: p.size,
            filter: "drop-shadow(0 0 6px rgba(34,211,238,0.8))",
          }}
          animate={{ y: [0, -12, 0], opacity: [0.35, 0.9, 0.35] }}
          transition={{ duration: p.dur, repeat: Infinity, delay: p.delay, ease: "easeInOut" }}
        />
      ))}
    </div>
  );
}
