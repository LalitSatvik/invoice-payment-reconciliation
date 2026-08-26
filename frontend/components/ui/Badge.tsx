import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export type BadgeVariant = "success" | "warning" | "danger" | "neutral" | "accent";

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

/**
 * Pill-shaped label for confidence bands and exception reasons. `variant`
 * is purely presentational - callers decide which variant a given
 * confidence score or exception reason maps to.
 */
const variantClass: Record<BadgeVariant, string> = {
  success: "bg-success-bg text-success",
  warning: "bg-warning-bg text-warning",
  danger: "bg-danger-bg text-danger",
  neutral: "bg-neutral-bg text-neutral",
  accent: "bg-accent-soft text-text",
};

export function Badge({ variant = "neutral", className, children, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-pill px-3 py-1 text-xs font-medium uppercase tracking-wide",
        variantClass[variant],
        className,
      )}
      {...props}
    >
      {children}
    </span>
  );
}
