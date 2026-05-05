"use client";
import { AnimatePresence, motion } from "framer-motion";
import { ImageOff, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { cn } from "../../lib/cn";

/**
 * Avatar thumbnail with:
 *   - server-side proxy fetch (avoids CDN hot-link blocks + Referer checks)
 *   - referrerpolicy=no-referrer (defence in depth even when proxied)
 *   - graceful onerror fallback to a placeholder
 *   - optional verified badge
 *   - click-to-zoom modal preview
 */
export function ImageThumb({
  src,
  alt,
  size = 56,
  rounded = "rounded-full",
  className,
  verified,
  zoom = true,
}: {
  src: string | null | undefined;
  alt?: string;
  size?: number;
  rounded?: string;
  className?: string;
  verified?: boolean;
  zoom?: boolean;
}) {
  const [broken, setBroken] = useState(false);
  const [open, setOpen] = useState(false);

  if (!src || broken) {
    return (
      <div
        className={cn(
          "flex items-center justify-center bg-white/[0.03] border border-white/5 text-slate-600",
          rounded,
          className,
        )}
        style={{ width: size, height: size }}
        aria-label={alt || "no image"}
      >
        <ImageOff className="w-1/3 h-1/3" />
      </div>
    );
  }

  const proxied = `/api/image?url=${encodeURIComponent(src)}`;

  return (
    <>
      <button
        type="button"
        onClick={() => zoom && setOpen(true)}
        className={cn(
          "relative shrink-0 group transition-transform",
          zoom && "hover:scale-105 cursor-zoom-in",
          rounded,
          "border border-white/10 overflow-hidden",
          className,
        )}
        style={{ width: size, height: size }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={proxied}
          alt={alt || ""}
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setBroken(true)}
          className="w-full h-full object-cover"
          style={{ display: "block" }}
        />
        {verified && (
          <span
            className="absolute -bottom-0.5 -right-0.5 w-4 h-4 rounded-full grid place-items-center bg-signal text-ink shadow"
            title="Verified avatar (matches across platforms)"
          >
            <ShieldCheck className="w-2.5 h-2.5" />
          </span>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-6"
            onClick={() => setOpen(false)}
          >
            <div className="absolute inset-0 bg-ink/85 backdrop-blur-md" />
            <motion.img
              initial={{ scale: 0.85, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.85, opacity: 0 }}
              transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
              src={proxied}
              alt={alt || ""}
              referrerPolicy="no-referrer"
              className="relative max-w-[90vw] max-h-[80vh] rounded-2xl border border-white/10 shadow-2xl"
            />
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
