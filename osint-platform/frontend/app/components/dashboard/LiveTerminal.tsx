"use client";
import { motion } from "framer-motion";
import { Terminal as TerminalIcon } from "lucide-react";
import { useEffect, useRef } from "react";
import { GlassCard, CardHeader } from "../ui/GlassCard";
import { tsShort } from "../../lib/format";
import type { TimelineEntry } from "../../lib/types";

const STAGE_COLOR: Record<string, string> = {
  init:    "text-slate-400",
  dorks:   "text-accent2",
  probe:   "text-accent",
  fetch:   "text-accent",
  recurse: "text-warn",
  rdap:    "text-signal",
  done:    "text-signal",
  error:   "text-danger",
};

export function LiveTerminal({
  entries,
  running,
}: {
  entries: TimelineEntry[];
  running: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight, behavior: "smooth" });
  }, [entries]);

  return (
    <GlassCard padding={false} className="h-full" id="stream">
      <div className="px-5 pt-5">
        <CardHeader
          title="Live Engine Stream"
          hint="server-sent events"
          action={
            <div className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-widest text-slate-500">
              <span className={`w-1.5 h-1.5 rounded-full ${running ? "bg-accent animate-pulse" : "bg-signal"}`} />
              {running ? "streaming" : "idle"}
            </div>
          }
        />
      </div>

      <div
        ref={ref}
        className="px-5 pb-5 max-h-72 overflow-y-auto bg-black/40 border-t border-white/5
                   font-mono text-[12px] leading-relaxed"
        style={{ fontVariantLigatures: "none" }}
      >
        <div className="pt-3 text-slate-500 select-none">
          $ osint <span className="text-accent">--engine=correlation</span> <span className="text-accent2">--mode=stream</span>
        </div>

        {entries.map((e, i) => {
          const color = STAGE_COLOR[e.stage] || "text-slate-300";
          return (
            <motion.div
              key={`${e.timestamp}-${i}`}
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.2 }}
              className="term-line py-[1px]"
            >
              <span className="text-slate-700">{tsShort(e.timestamp)}</span>{" "}
              <span className={`${color}`}>[{e.stage.padEnd(7)}]</span>{" "}
              <span className="text-slate-300">{e.detail}</span>
            </motion.div>
          );
        })}

        {running && (
          <div className="term-line text-slate-500 term-cursor">awaiting next event</div>
        )}
        {!running && entries.length === 0 && (
          <div className="term-line text-slate-600 mt-2"># no events yet — run a search to populate the feed</div>
        )}
      </div>
    </GlassCard>
  );
}
