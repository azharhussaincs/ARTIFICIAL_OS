"use client";
import { Globe, AlertTriangle } from "lucide-react";
import { GlassCard, CardHeader } from "../ui/GlassCard";
import type { ExternalOsintBlock } from "../../lib/types";

interface Props {
  block?: ExternalOsintBlock;
}

// Header-only banner for the OSINT FINDINGS (UNVERIFIED) section. Sits
// between the authoritative LOCAL DB panel and the existing dashboard
// blocks (FindingsList, IdentityGraph, Snapshots, Dorks, WHOIS) so the
// user-spec'd dual-section layout is visually enforced:
//
//   🟢 VERIFIED LOCAL DATABASE (100% TRUST)
//   ─────────────────────────────────────────
//   🌐 OSINT FINDINGS (UNVERIFIED)
//
// All concrete OSINT panels render below this banner.
export function OsintFindingsBanner({ block }: Props) {
  const stats   = block?.stats;
  const skipped = !!block?.skipped;
  return (
    <GlassCard className="border-amber-400/20">
      <CardHeader
        title="OSINT FINDINGS"
        hint="unverified · evidence-based"
        action={
          <span className="inline-flex items-center gap-1 text-[10px] font-mono uppercase tracking-[0.18em] text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-md px-2 py-1">
            <AlertTriangle className="w-3 h-3" />
            UNVERIFIED
          </span>
        }
      />

      <div className="flex items-start gap-3 text-[12px] text-slate-300">
        <Globe className="w-4 h-4 mt-0.5 text-slate-400 shrink-0" />
        <div className="space-y-1">
          <div className="font-mono">
            External OSINT is supporting intelligence only — never overrides local DB.
          </div>
          {skipped ? (
            <div className="text-amber-300/80 font-mono text-[11px]">
              {block?.empty_message || "External OSINT skipped — DB returned authoritative data."}
            </div>
          ) : stats ? (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mt-2 font-mono text-[11px]">
              <Stat label="Total"      value={stats.total_findings} />
              <Stat label="Verified"   value={stats.verified_profiles} />
              <Stat label="Usernames"  value={stats.usernames} />
              <Stat label="Emails"     value={stats.emails} />
              <Stat label="Confidence" value={`${stats.confidence_score}/100`} />
            </div>
          ) : null}
        </div>
      </div>
    </GlassCard>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-md border border-white/5 bg-white/[0.03] px-2 py-1.5">
      <div className="text-[9px] uppercase tracking-[0.14em] text-slate-500">{label}</div>
      <div className="text-slate-200">{value}</div>
    </div>
  );
}
