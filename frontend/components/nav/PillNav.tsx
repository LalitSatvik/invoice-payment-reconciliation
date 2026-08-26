"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface PillNavItem {
  href: string;
  label: string;
  icon: ReactNode;
}

export interface PillNavProps {
  items: PillNavItem[];
  /** Override active-item detection instead of matching the current pathname. */
  activeHref?: string;
  className?: string;
}

/**
 * Icon-only, rounded-full pill navigation bar. The active item gets the
 * accent background with black icon/text; inactive items are muted and
 * pick up a light neutral background on hover.
 */
export function PillNav({ items, activeHref, className }: PillNavProps) {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Primary"
      className={cn(
        "inline-flex items-center gap-1 rounded-pill border border-border bg-surface p-1.5 shadow-card",
        className,
      )}
    >
      {items.map((item) => {
        const isActive = (activeHref ?? pathname) === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-label={item.label}
            title={item.label}
            aria-current={isActive ? "page" : undefined}
            className={cn(
              "flex h-11 w-11 items-center justify-center rounded-pill transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-text/70 focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
              isActive
                ? "bg-accent text-text"
                : "text-text-muted hover:bg-bg hover:text-text",
            )}
          >
            {item.icon}
          </Link>
        );
      })}
    </nav>
  );
}
