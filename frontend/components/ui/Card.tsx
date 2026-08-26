import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** Disable the standard p-6 interior padding, e.g. when a child manages its own. */
  noPadding?: boolean;
}

/**
 * White, rounded, minimally-shadowed surface - the base container for the
 * flat/clean aesthetic. No hover treatment by default; interactive cards
 * should opt in via their own className.
 */
export function Card({ className, noPadding, children, ...props }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-card bg-surface border border-border shadow-card",
        !noPadding && "p-6",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}
