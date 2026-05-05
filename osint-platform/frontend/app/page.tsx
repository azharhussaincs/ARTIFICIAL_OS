"use client";
import { motion } from "framer-motion";
import { CheckCircle2, Database, Globe, Hash, Image as ImageIcon, Mail, Network, Phone, ShieldCheck, Sparkles } from "lucide-react";
import { useState } from "react";

// Shell
import { Sidebar } from "./components/shell/Sidebar";
import { TopBar } from "./components/shell/TopBar";
import { CommandPalette } from "./components/shell/CommandPalette";

// Hero
import { SearchHero } from "./components/hero/SearchHero";

// Dashboard
import { MetricCard } from "./components/dashboard/MetricCard";
import { ConfidenceRing } from "./components/dashboard/ConfidenceRing";
import { FindingsList } from "./components/dashboard/FindingsList";
import { Timeline } from "./components/dashboard/Timeline";
import { IdentityGraph } from "./components/dashboard/IdentityGraph";
import { LiveTerminal } from "./components/dashboard/LiveTerminal";
import { DorksPanel } from "./components/dashboard/DorksPanel";
import { WhoisPanel } from "./components/dashboard/WhoisPanel";
import { SnapshotsPanel } from "./components/dashboard/SnapshotsPanel";
import { HistoryPanel } from "./components/dashboard/HistoryPanel";
import { ImageClustersPanel } from "./components/dashboard/ImageClustersPanel";
import { EvidenceLedger } from "./components/dashboard/EvidenceLedger";
import { LocalDatabasePanel } from "./components/dashboard/LocalDatabasePanel";
import { OsintFindingsBanner } from "./components/dashboard/OsintFindingsBanner";
import { GlassCard, CardHeader } from "./components/ui/GlassCard";

// State
import { useSearchStream } from "./hooks/useSearchStream";
import type { QueryKind, SearchBundleInput, SearchResponse } from "./lib/types";

export default function Page() {
  const stream = useSearchStream();
  const [historyTick, setHistoryTick] = useState(0);

  function onRun(kind: QueryKind, value: string, opts: { live: boolean }) {
    stream.run(kind, value, opts).then(() => setHistoryTick((t) => t + 1));
  }

  function onRunBundle(bundle: SearchBundleInput) {
    stream.runBundle(bundle).then(() => setHistoryTick((t) => t + 1));
  }

  function loadFromHistory(r: SearchResponse) {
    stream.commit(r);
    setTimeout(() => document.querySelector("#findings")?.scrollIntoView({ behavior: "smooth" }), 100);
  }

  const { state, result, findings, snapshots, timeline, error } = stream;
  const summary = result?.summary || {};
  const verifiedCount = (summary as { verified_count?: number }).verified_count ?? findings.filter((f) => f.verified).length;
  const high          = (summary as { high_confidence_count?: number }).high_confidence_count ?? findings.filter((f) => f.confidence >= 90).length;
  const suppressed    = (summary as { suppressed_count?: number }).suppressed_count ?? 0;
  const avatarCount   = snapshots.filter((s) => s.avatar_url).length;
  const clusterCount  = result?.image_clusters?.length ?? 0;
  const imageFindings = findings.filter((f) => f.type === "image").length;

  const showDashboard = state !== "idle" || findings.length > 0;

  return (
    <div className="min-h-screen flex">
      <Sidebar />
      <CommandPalette />

      <div className="flex-1 min-w-0 flex flex-col">
        <TopBar liveState={state} />

        {/* Hero / search */}
        <SearchHero onRun={onRun} onRunBundle={onRunBundle} running={state === "running"} />

        {/* Dashboard */}
        {showDashboard && (
          <main className="px-5 md:px-8 pb-16 space-y-8">

            {/* Metrics row + confidence ring */}
            <section className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-6 items-stretch">
              <GlassCard className="flex flex-col items-center justify-center">
                <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-slate-500 mb-3">
                  Identity Confidence
                </div>
                <ConfidenceRing
                  value={result?.confidence_score ?? 0}
                  label={result?.confidence_label ?? "weak"}
                />
                <div className="mt-3 text-[11px] font-mono text-slate-500">
                  avg of top-5 findings
                </div>
              </GlassCard>

              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <MetricCard label="Findings"   value={findings.length}            icon={Database}     delay={0.05} />
                <MetricCard label="Verified"   value={verifiedCount}              icon={CheckCircle2} accent="signal" delay={0.10} />
                <MetricCard label="High-conf"  value={high}                       icon={Sparkles}     accent="violet" delay={0.15} />
                <MetricCard label="Usernames"  value={findings.filter(f => f.type === "username" && f.confidence >= 50).length} icon={Hash}  delay={0.20} />
                <MetricCard label="Emails"     value={findings.filter(f => f.type === "email"    && f.confidence >= 50).length} icon={Mail}  accent="signal" delay={0.25} />
                <MetricCard label="Profiles"   value={findings.filter(f => f.type === "social_profile").length}                  icon={Globe} accent="violet" delay={0.30} />
                <MetricCard label="Domains"    value={findings.filter(f => f.type === "domain"   && f.confidence >= 50).length} icon={Network} delay={0.35} />
                <MetricCard label="Phones"     value={findings.filter(f => f.type === "phone"    && f.confidence >= 50).length} icon={Phone}   accent="warn" delay={0.40} />
                <MetricCard label="Suppressed" value={suppressed}                                 icon={ShieldCheck} accent="warn" hint="noise filtered" delay={0.45} />
              </div>
            </section>

            {/* Image-pipeline diagnostics strip */}
            <section className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <MetricCard label="Avatars extracted" value={avatarCount} icon={ImageIcon} accent="signal" hint={`from ${snapshots.length} fetched profile(s)`} delay={0.05} />
              <MetricCard label="Image clusters" value={clusterCount} icon={Sparkles} accent="violet" hint="cross-platform avatar matches" delay={0.10} />
              <MetricCard label="Image findings" value={imageFindings} icon={ShieldCheck} hint="dedupe-keyed by perceptual hash" delay={0.15} />
            </section>

            {/* Error banner */}
            {error && state === "error" && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="rounded-xl p-3 border border-danger/40 bg-danger/10 text-danger font-mono text-sm">
                ▲ {error}
              </motion.div>
            )}

            {/* === SECTION 1 — VERIFIED LOCAL DATABASE (100% TRUST) ===
                Authoritative ES tc_index hits. ALWAYS rendered first;
                shows the spec'd "❌ No data found" message when empty so
                analysts never confuse 'no DB section' with 'DB skipped'. */}
            <LocalDatabasePanel block={result?.local_db} />

            {/* === SECTION 2 — OSINT FINDINGS (UNVERIFIED) ===
                Banner that introduces the unverified evidence layer; the
                concrete OSINT panels (FindingsList, IdentityGraph,
                Snapshots, Dorks, WHOIS) all render below it. */}
            <OsintFindingsBanner block={result?.external_osint} />

            {/* Findings */}
            <FindingsList findings={findings} snapshots={snapshots} recordId={result?.id} />

            {/* Graph + timeline + terminal */}
            <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2">
                <IdentityGraph
                  findings={findings}
                  seedKey={result?.graph?.seed}
                  graphEdges={result?.graph?.edges}
                />
              </div>
              <div className="space-y-6">
                <Timeline entries={timeline} />
                <LiveTerminal entries={timeline} running={state === "running"} />
              </div>
            </section>

            {/* Image clusters (cross-platform avatar matches) */}
            {(result?.image_clusters?.length ?? 0) > 0 && (
              <ImageClustersPanel clusters={result?.image_clusters ?? []} />
            )}

            {/* Evidence ledger — chronological signal audit */}
            {(result?.evidence_ledger?.length ?? 0) > 0 && (
              <EvidenceLedger rows={result?.evidence_ledger ?? []} />
            )}

            {/* Snapshots */}
            {snapshots.length > 0 && <SnapshotsPanel snaps={snapshots} />}

            {/* Dorks + WHOIS */}
            <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <DorksPanel dorks={result?.dorks ?? []} />
              <WhoisPanel records={result?.whois_records ?? []} />
            </section>
          </main>
        )}

        <div className="px-5 md:px-8 pb-16">
          <HistoryPanel onPick={loadFromHistory} refreshKey={historyTick} />
        </div>

        <footer className="border-t border-white/5 px-5 md:px-8 py-5 text-xs text-slate-500 flex flex-wrap items-center justify-between gap-2">
          <div>© OSINT Platform — for ethical, lawful intelligence work only.</div>
          <div className="font-mono">v1.2.0 · <a href="/docs" className="text-accent hover:underline">/docs</a></div>
        </footer>
      </div>
    </div>
  );
}
