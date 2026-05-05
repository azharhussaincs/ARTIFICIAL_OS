"use client";
import { useEffect } from "react";

type Combo = { key: string; meta?: boolean; ctrl?: boolean; shift?: boolean };

/**
 * Global keyboard shortcuts.
 *   useKeyboard({ key: "k", meta: true }, () => openCmd())
 *   useKeyboard({ key: "/" }, () => focusSearch())
 *
 * Ignores keypresses that originate from text inputs unless allowInInput.
 */
export function useKeyboard(combo: Combo, handler: () => void, allowInInput = false) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!allowInInput) {
        const t = e.target as HTMLElement | null;
        if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      }
      if (combo.meta && !(e.metaKey || e.ctrlKey)) return;
      if (combo.ctrl && !e.ctrlKey) return;
      if (combo.shift && !e.shiftKey) return;
      if (e.key.toLowerCase() !== combo.key.toLowerCase()) return;
      e.preventDefault();
      handler();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [combo.key, combo.meta, combo.ctrl, combo.shift, handler, allowInInput]);
}
