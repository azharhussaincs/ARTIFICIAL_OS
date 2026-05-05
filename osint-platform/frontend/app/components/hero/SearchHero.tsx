"use client";
import { motion } from "framer-motion";
import { Radar, Sparkles, Zap } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NeonButton } from "../ui/NeonButton";
import { ScannerOverlay } from "../ui/ScannerOverlay";
import { BackgroundFX } from "./BackgroundFX";
import { KindTabs, KIND_PLACEHOLDER } from "./KindTabs";
import { useUI, ui } from "../../store/uiStore";
import type { QueryKind, SearchBundleInput } from "../../lib/types";
import { useKeyboard } from "../../hooks/useKeyboard";
import { MultiInputForm } from "./MultiInputForm";

interface Props {
  onRun: (kind: QueryKind, value: string, opts: { live: boolean }) => void;
  onRunBundle: (bundle: SearchBundleInput) => void;
  running: boolean;
}

const TYPED_WORDS = ["a name.", "an email.", "a phone.", "a username."];

export function SearchHero({ onRun, onRunBundle, running }: Props) {
  const kind = useUI((s) => s.kind);
  const live = useUI((s) => s.live);
  const [value, setValue] = useState("");
  const [typed, setTyped] = useState("");
  const [wordIdx, setWordIdx] = useState(0);
  const [erasing, setErasing] = useState(false);
  const [multiOpen, setMultiOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // "/" focuses the input
  useKeyboard({ key: "/" }, () => inputRef.current?.focus());

  // Typing animation in the headline
  useEffect(() => {
    const word = TYPED_WORDS[wordIdx];
    const speed = erasing ? 40 : 70;
    const t = setTimeout(() => {
      if (!erasing) {
        if (typed.length < word.length) setTyped(word.slice(0, typed.length + 1));
        else setTimeout(() => setErasing(true), 1100);
      } else {
        if (typed.length > 0) setTyped(word.slice(0, typed.length - 1));
        else { setErasing(false); setWordIdx((w) => (w + 1) % TYPED_WORDS.length); }
      }
    }, speed);
    return () => clearTimeout(t);
  }, [typed, erasing, wordIdx]);

  function submit() {
    const v = value.trim();
    if (!v || running) return;
    onRun(kind, v, { live });
  }

  return (
    <section id="search" className="relative pb-12 pt-10 md:pt-16 px-5 md:px-8">
      <BackgroundFX />

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="max-w-5xl mx-auto"
      >
        {/* Eyebrow */}
        <div className="flex items-center gap-3 text-xs font-mono uppercase tracking-[0.3em] text-accent/80">
          <Radar className="w-3.5 h-3.5" />
          <span>cross-identity correlation</span>
          <span className="ml-2 inline-flex items-center gap-1 text-slate-500">
            <Sparkles className="w-3 h-3 text-accent2" /> live engine
          </span>
        </div>

        {/* Headline with type effect */}
        <h1 className="mt-4 font-display font-semibold text-3xl md:text-5xl tracking-tight text-balance leading-tight">
          Drop in&nbsp;
          <span className="text-accent">{typed}</span>
          <span className="text-accent term-cursor" />
          <br />
          <span className="text-slate-400">Get back </span>
          <span className="bg-clip-text text-transparent bg-gradient-to-r from-accent to-accent2">
            verified connected identities.
          </span>
        </h1>

        <p className="mt-4 text-slate-400 max-w-2xl text-sm md:text-base">
          The engine probes public profile sites, fetches confirmed profiles, mines bios for
          cross-platform handles, looks up RDAP records, and merges every source into one
          <span className="text-accent2 font-medium"> Finding</span> per identity — each scored,
          each with reasons.
        </p>

        {/* Search panel */}
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="mt-8 glass-strong rounded-2xl p-5 md:p-7 relative neon-border"
        >
          <ScannerOverlay active={running} />

          <KindTabs
            value={kind}
            onChange={(k) => { ui.set({ kind: k }); setValue(""); inputRef.current?.focus(); }}
          />

          <div className="mt-5 flex flex-col md:flex-row gap-3">
            <div className="relative flex-1">
              <div
                className={`absolute inset-0 rounded-xl pointer-events-none transition-opacity ${
                  running ? "opacity-100" : "opacity-0"
                }`}
                style={{
                  boxShadow: "0 0 0 1px rgba(34,211,238,0.6), 0 0 32px rgba(34,211,238,0.35)",
                }}
              />
              <input
                id="query-input"
                ref={inputRef}
                value={value}
                onChange={(e) => setValue(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit()}
                placeholder={KIND_PLACEHOLDER[kind]}
                autoComplete="off"
                spellCheck={false}
                className="w-full bg-ink/70 border border-white/5 rounded-xl px-5 py-4 font-mono text-sm md:text-base
                           placeholder:text-slate-600 outline-none focus:border-accent/60
                           transition-colors duration-200"
              />
              <div className="absolute right-4 top-1/2 -translate-y-1/2 text-[10px] font-mono text-slate-600 pointer-events-none">
                press <kbd className="px-1 py-0.5 rounded border border-white/10">/</kbd> to focus
              </div>
            </div>

            <NeonButton onClick={submit} disabled={running || !value.trim()} loading={running}>
              <Zap className="w-4 h-4" />
              {running ? "Scanning…" : "Run search"}
            </NeonButton>
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500">
            <div className="flex items-center gap-2">
              <span className="inline-flex w-1.5 h-1.5 rounded-full bg-signal" />
              public sources only · respects robots.txt · no login bypass
            </div>
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={live}
                onChange={(e) => ui.set({ live: e.target.checked })}
                className="accent-accent"
              />
              <span>Live stream (SSE)</span>
            </label>
          </div>

          <MultiInputForm
            open={multiOpen}
            onToggle={() => setMultiOpen((v) => !v)}
            running={running}
            onRun={onRunBundle}
          />
        </motion.div>
      </motion.div>
    </section>
  );
}
