"use client";
import { motion, type HTMLMotionProps } from "framer-motion";
import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

type Variant = "primary" | "ghost";

type ButtonProps = Omit<HTMLMotionProps<"button">, "ref" | "children"> & {
  variant?: Variant;
  loading?: boolean;
  children?: ReactNode;
};

export function NeonButton({
  variant = "primary",
  loading,
  className,
  children,
  ...rest
}: ButtonProps) {
  return (
    <motion.button
      whileTap={{ scale: 0.97 }}
      className={cn(variant === "primary" ? "btn-primary" : "btn-ghost", className)}
      {...rest}
    >
      {loading && (
        <span
          className="inline-block w-3 h-3 rounded-full border-2 border-current border-t-transparent animate-spin"
          aria-hidden
        />
      )}
      {children}
    </motion.button>
  );
}
