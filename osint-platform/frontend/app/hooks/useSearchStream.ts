"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, streamSearch } from "../lib/api";
import type {
  Finding, ProfileSnapshot, QueryKind, SearchBundleInput, SearchResponse, StreamEvent, TimelineEntry,
} from "../lib/types";

export type StreamState = "idle" | "running" | "complete" | "error";

export interface SearchStreamSnapshot {
  state: StreamState;
  result: SearchResponse | null;
  findings: Finding[];                // live, deduplicated by key
  snapshots: ProfileSnapshot[];
  timeline: TimelineEntry[];
  logs: string[];                     // raw "[stage] detail" lines
  error: string | null;
}

const EMPTY: SearchStreamSnapshot = {
  state: "idle",
  result: null,
  findings: [],
  snapshots: [],
  timeline: [],
  logs: [],
  error: null,
};

/**
 * Drives a live SSE search OR a one-shot POST search.
 *  - run(kind, value, { live: true })  → opens EventSource, streams events
 *  - run(kind, value, { live: false }) → single POST, then commits result
 */
export function useSearchStream() {
  const [snap, setSnap] = useState<SearchStreamSnapshot>(EMPTY);
  const sseRef = useRef<EventSource | null>(null);

  const close = useCallback(() => {
    sseRef.current?.close();
    sseRef.current = null;
  }, []);

  useEffect(() => () => close(), [close]);

  const ingestFinding = useCallback((f: Finding) => {
    setSnap((s) => {
      const idx = s.findings.findIndex((x) => x.key === f.key);
      const next = idx >= 0
        ? Object.assign([...s.findings], { [idx]: f })
        : [...s.findings, f];
      next.sort((a, b) => b.confidence - a.confidence);
      return { ...s, findings: next };
    });
  }, []);

  const run = useCallback(
    async (kind: QueryKind, value: string, opts: { live?: boolean } = {}) => {
      close();
      setSnap({ ...EMPTY, state: "running" });

      if (opts.live === false) {
        try {
          const result = await api.search(kind, value);
          setSnap({
            state: "complete",
            result,
            findings: result.findings,
            snapshots: result.profile_snapshots,
            timeline: result.timeline,
            logs: result.timeline.map((t) => `[${t.stage}] ${t.detail}`),
            error: null,
          });
        } catch (e) {
          setSnap((s) => ({ ...s, state: "error", error: (e as Error).message }));
        }
        return;
      }

      const sse = streamSearch(kind, value);
      sseRef.current = sse;

      sse.addEventListener("stage", (e) => {
        const d = JSON.parse((e as MessageEvent).data) as Extract<StreamEvent, { type: "stage" }>;
        setSnap((s) => ({
          ...s,
          logs: [...s.logs, `[${d.stage}] ${d.detail}`],
          timeline: [...s.timeline, { timestamp: new Date().toISOString(), stage: d.stage, detail: d.detail }],
        }));
      });

      sse.addEventListener("finding", (e) => {
        const d = JSON.parse((e as MessageEvent).data) as Extract<StreamEvent, { type: "finding" }>;
        ingestFinding(d.finding);
      });

      sse.addEventListener("snapshot", (e) => {
        const d = JSON.parse((e as MessageEvent).data) as Extract<StreamEvent, { type: "snapshot" }>;
        setSnap((s) => ({ ...s, snapshots: [...s.snapshots, d.snapshot] }));
      });

      sse.addEventListener("complete", (e) => {
        const d = JSON.parse((e as MessageEvent).data) as Extract<StreamEvent, { type: "complete" }>;
        setSnap((s) => ({
          ...s,
          state: "complete",
          result: d.payload,
          findings: d.payload.findings,
          snapshots: d.payload.profile_snapshots,
          timeline: d.payload.timeline,
          error: null,
        }));
        close();
      });

      sse.addEventListener("error", () => {
        setSnap((s) => (s.state === "complete" ? s : { ...s, state: "error", error: "stream disconnected" }));
        close();
      });
    },
    [close, ingestFinding],
  );

  const reset = useCallback(() => {
    close();
    setSnap(EMPTY);
  }, [close]);

  const runBundle = useCallback(async (bundle: SearchBundleInput) => {
    close();
    setSnap({ ...EMPTY, state: "running" });
    try {
      const result = await api.searchBundle(bundle);
      setSnap({
        state: "complete",
        result,
        findings: result.findings,
        snapshots: result.profile_snapshots,
        timeline: result.timeline,
        logs: result.timeline.map((t) => `[${t.stage}] ${t.detail}`),
        error: null,
      });
    } catch (e) {
      setSnap((s) => ({ ...s, state: "error", error: (e as Error).message }));
    }
  }, [close]);

  /** Inject a finished SearchResponse — used when replaying from history. */
  const commit = useCallback((r: SearchResponse) => {
    close();
    setSnap({
      state: "complete",
      result: r,
      findings: r.findings,
      snapshots: r.profile_snapshots,
      timeline: r.timeline,
      logs: r.timeline.map((t) => `[${t.stage}] ${t.detail}`),
      error: null,
    });
  }, [close]);

  return useMemo(
    () => ({ ...snap, run, runBundle, reset, commit }),
    [snap, run, runBundle, reset, commit],
  );
}
