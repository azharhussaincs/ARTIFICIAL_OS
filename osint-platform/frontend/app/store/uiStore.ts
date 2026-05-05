"use client";
import { useSyncExternalStore } from "react";
import type { QueryKind } from "../lib/types";

interface UIState {
  kind: QueryKind;
  query: string;
  live: boolean;
  filterType: "" | "username" | "email" | "phone" | "name" | "social_profile" | "website" | "domain";
  filterMinConf: number;
  filterVerifiedOnly: boolean;
  showSignals: boolean;
  cmdOpen: boolean;
  sidebarOpen: boolean;
}

const initial: UIState = {
  kind: "name",
  query: "",
  live: true,
  filterType: "",
  filterMinConf: 50,
  filterVerifiedOnly: false,
  showSignals: true,
  cmdOpen: false,
  sidebarOpen: false,
};

let state: UIState = initial;
const listeners = new Set<() => void>();

export const ui = {
  get(): UIState { return state; },
  set(patch: Partial<UIState>) {
    state = { ...state, ...patch };
    listeners.forEach((l) => l());
  },
  subscribe(fn: () => void) {
    listeners.add(fn);
    return () => { listeners.delete(fn); };
  },
};

export function useUI<T>(selector: (s: UIState) => T): T {
  return useSyncExternalStore(ui.subscribe, () => selector(ui.get()), () => selector(initial));
}
