"use client";
import { AnimatePresence, motion } from "framer-motion";
import {
  AtSign, ChevronDown, Globe, Hash, Image as ImageIcon, Link2, Phone, ShieldCheck, User, UserCheck,
} from "lucide-react";
import { useMemo, useState } from "react";
import type { Finding, FindingType, ProfileSnapshot } from "../../lib/types";
import { cn } from "../../lib/cn";
import { confClass, shortHost, TYPE_LABEL } from "../../lib/format";
import { VerifiedBadge } from "../ui/Badge";
import { ImageThumb } from "../ui/ImageThumb";
import { SignalTrail } from "./SignalTrail";

const ICONS: Record<FindingType, React.ComponentType<{ className?: string }>> = {
  name:           User,
  username:       Hash,
  email:          AtSign,
  phone:          Phone,
  social_profile: UserCheck,
  website:        Globe,
  domain:         Link2,
  person:         User,
  image:          ImageIcon,
};

function linkFor(f: Finding): string | null {
  if (f.type === "email")   return `mailto:${f.value}`;
  if (f.type === "phone")   return `tel:${f.value}`;
  if (f.type === "website") return f.value;
  if (f.type === "social_profile") return f.value;
  if (f.type === "domain")  return `https://${f.value}`;
  return null;
}

export function FindingCard({
  f, showSignals = true, index = 0, snapshots = [],
}: {
  f: Finding;
  showSignals?: boolean;
  index?: number;
  snapshots?: ProfileSnapshot[];
}) {
  const [open, setOpen] = useState(false);
  const Icon = ICONS[f.type] ?? Globe;
  const href = linkFor(f);
  const total = f.signals.reduce((a, s) => a + s.delta, 0);

  // For social_profile findings, find the matching snapshot to show its avatar
  // For username findings, surface any of the linked profiles' avatars
  const avatar = useMemo<string | null>(() => {
    if (f.type === "social_profile") {
      const s = snapshots.find((s) => s.url === f.value);
      return s?.avatar_url ?? null;
    }
    if (f.type === "username") {
      const handle = f.value.toLowerCase();
      const s = snapshots.find((s) => (s.handle || "").toLowerCase() === handle && s.avatar_url);
      return s?.avatar_url ?? null;
    }
    if (f.type === "image") {
      // The "image" finding's value is "sha:<hash>" — look for any snapshot
      // referenced via related_to keys (social_profile::URL).
      const profileUrls = new Set(
        f.related_to.filter((k) => k.startsWith("social_profile::")).map((k) => k.split("::", 2)[1]),
      );
      const s = snapshots.find((s) => profileUrls.has(s.url) && s.avatar_url);
      return s?.avatar_url ?? null;
    }
    return null;
  }, [f, snapshots]);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: Math.min(index, 12) * 0.025, ease: [0.16, 1, 0.3, 1] }}
      whileHover={{ y: -2 }}
      className={cn(
        "glass rounded-xl p-4 relative overflow-hidden neon-border",
        f.verified && "ring-1 ring-signal/30",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          {avatar ? (
            <ImageThumb
              src={avatar}
              alt={f.value}
              size={36}
              rounded="rounded-lg"
              verified={f.verified}
            />
          ) : (
            <div
              className="w-9 h-9 rounded-lg grid place-items-center bg-white/[0.03] border border-white/5"
              style={{ color: "#22d3ee" }}
            >
              <Icon className="w-4 h-4" />
            </div>
          )}
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono uppercase tracking-[0.16em] text-slate-500">
                {TYPE_LABEL[f.type]}
              </span>
              <VerifiedBadge verified={f.verified} />
            </div>
            {href ? (
              <a
                href={href}
                target="_blank"
                rel="noopener"
                className="block font-mono text-[13px] text-slate-100 hover:text-accent truncate transition"
                title={f.value}
              >
                {f.value}
              </a>
            ) : (
              <div className="font-mono text-[13px] text-slate-100 truncate">{f.value}</div>
            )}
          </div>
        </div>

        <div className="flex flex-col items-end gap-2">
          <span className={cn("conf-pill", confClass(f.label))}>
            {f.confidence} · {f.label}
          </span>
          {/* Confidence bar */}
          <div className="w-20 h-1 rounded-full bg-white/5 overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${f.confidence}%` }}
              transition={{ duration: 0.5, ease: "easeOut" }}
              className="h-full"
              style={{ background: "linear-gradient(90deg, #22d3ee, #a78bfa)" }}
            />
          </div>
        </div>
      </div>

      {/* Toggle for signal trail / sources */}
      {(f.signals.length > 0 || f.sources.length > 0) && (
        <button
          onClick={() => setOpen((v) => !v)}
          className="mt-3 flex items-center gap-1 text-[11px] font-mono text-slate-500 hover:text-accent transition"
        >
          <ChevronDown className={cn("w-3 h-3 transition-transform", open && "rotate-180")} />
          {open ? "hide evidence" : "show evidence"} · {f.signals.length} signals · {f.sources.length} sources
        </button>
      )}

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="trail"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25 }}
            className="mt-3 space-y-3"
          >
            {showSignals && <SignalTrail signals={f.signals} total={total} />}
            {f.sources.length > 0 && (
              <div className="border-t border-white/5 pt-2">
                <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-slate-500 mb-1.5">
                  sources
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {f.sources.map((s, i) => (
                    s.url.startsWith("urn:") ? (
                      <span key={i} className="px-2 py-0.5 rounded text-[10px] font-mono border border-white/5 text-slate-500">
                        {s.source_type}
                      </span>
                    ) : (
                      <a key={i} href={s.url} target="_blank" rel="noopener"
                         className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono
                                    border border-white/5 text-slate-300 hover:border-accent hover:text-accent transition">
                        <ShieldCheck className="w-2.5 h-2.5" />
                        {s.source_type} · {shortHost(s.url)}
                      </a>
                    )
                  ))}
                </div>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
