"use client";
import { motion } from "framer-motion";
import { ExternalLink, ShieldOff } from "lucide-react";
import type { ProfileSnapshot } from "../../lib/types";
import { GlassCard, CardHeader } from "../ui/GlassCard";
import { ImageThumb } from "../ui/ImageThumb";

export function SnapshotsPanel({ snaps }: { snaps: ProfileSnapshot[] }) {
  return (
    <GlassCard padding={false}>
      <div className="px-5 pt-5">
        <CardHeader title="Profile Snapshots" hint={`${snaps.length} profiles`} />
      </div>
      <div className="px-5 pb-5 grid grid-cols-1 md:grid-cols-2 gap-3">
        {snaps.map((s, i) => (
          <motion.div
            key={s.url}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25, delay: Math.min(i, 8) * 0.03 }}
            whileHover={{ y: -2 }}
            className="rounded-xl border border-white/5 bg-white/[0.02] hover:bg-white/[0.04] p-3 flex gap-3 transition group"
          >
            <ImageThumb src={s.avatar_url ?? null} alt={s.platform} size={56} />
            <a
              href={s.url}
              target="_blank"
              rel="noopener"
              className="flex-1 min-w-0 block"
            >
              <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.16em] text-accent">
                <span>{s.platform}/{s.handle}</span>
                {s.is_blocked && (
                  <span className="inline-flex items-center gap-1 text-warn normal-case tracking-normal">
                    <ShieldOff className="w-3 h-3" /> blocked
                  </span>
                )}
                <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 transition ml-auto" />
              </div>
              <div className="font-display font-semibold text-slate-100 truncate">
                {s.display_name || (s.is_blocked ? "[content blocked]" : "—")}
              </div>
              <div className="text-[12px] text-slate-400 line-clamp-2 leading-snug mt-0.5">
                {s.bio || (s.is_blocked ? "Login wall — only avatar/og:image extracted." : "")}
              </div>
            </a>
          </motion.div>
        ))}
        {!snaps.length && <div className="md:col-span-2 text-sm text-slate-600 font-mono">// no profile snapshots captured</div>}
      </div>
    </GlassCard>
  );
}
