"use client";
import { AnimatePresence, motion } from "framer-motion";

export function ScannerOverlay({ active }: { active: boolean }) {
  return (
    <AnimatePresence>
      {active && (
        <motion.div
          className="scanner"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          aria-hidden
        />
      )}
    </AnimatePresence>
  );
}
