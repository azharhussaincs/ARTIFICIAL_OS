"use client";
import { motion } from "framer-motion";
import { Camera, Fingerprint } from "lucide-react";
import type { ImageCluster } from "../../lib/types";
import { GlassCard, CardHeader } from "../ui/GlassCard";
import { ImageThumb } from "../ui/ImageThumb";

export function ImageClustersPanel({ clusters }: { clusters: ImageCluster[] }) {
  if (!clusters.length) return null;
  return (
    <GlassCard padding={false}>
      <div className="px-5 pt-5">
        <CardHeader
          title="Avatar Image Matches"
          hint={`${clusters.length} cluster${clusters.length === 1 ? "" : "s"} · perceptual hash`}
          action={
            <span className="text-[10px] font-mono text-slate-500 inline-flex items-center gap-1">
              <Fingerprint className="w-3 h-3 text-accent2" /> dHash · Hamming ≤ 12
            </span>
          }
        />
      </div>
      <div className="px-5 pb-5 space-y-4">
        {clusters.map((c, i) => (
          <motion.div
            key={c.representative_hash_hex}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: i * 0.05 }}
            className="rounded-xl border border-signal/20 bg-signal/[0.04] p-3"
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-[0.16em] text-signal">
                <Camera className="w-3.5 h-3.5" />
                same avatar on {c.platforms.length} platform{c.platforms.length === 1 ? "" : "s"}
              </div>
              <span className="text-[10px] font-mono text-slate-500">
                hash 0x{c.representative_hash_hex.slice(0, 12)}…
              </span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
              {c.members.map((m) => (
                <div
                  key={m.avatar_url}
                  className="rounded-lg border border-white/5 bg-ink/40 p-2 hover:border-signal/50 transition group"
                >
                  <div className="aspect-square w-full">
                    <ImageThumb
                      src={m.avatar_url}
                      alt={`${m.platform}/${m.handle}`}
                      size={140}
                      rounded="rounded-md"
                      className="!w-full !h-full"
                      verified
                    />
                  </div>
                  {m.profile_url ? (
                    <a
                      href={m.profile_url}
                      target="_blank"
                      rel="noopener"
                      className="block mt-1.5 text-[10px] font-mono uppercase tracking-[0.12em] text-accent hover:text-accent2 transition"
                    >
                      {m.platform}/{m.handle ?? ""}
                    </a>
                  ) : (
                    <div className="mt-1.5 text-[10px] font-mono uppercase tracking-[0.12em] text-accent">
                      {m.platform}/{m.handle ?? ""}
                    </div>
                  )}
                  <div className="text-[10px] font-mono text-slate-500">
                    Δ {m.min_distance} bits
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        ))}
      </div>
    </GlassCard>
  );
}
