import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface KpiStatProps {
  label: string;
  value: ReactNode;
  /** Optional supporting delta, e.g. "+4.2% vs last week". */
  delta?: string;
  deltaTone?: "positive" | "negative" | "neutral";
  icon?: ReactNode;
  className?: string;
}

const deltaToneClass: Record<NonNullable<KpiStatProps["deltaTone"]>, string> = {
  positive: "text-success",
  negative: "text-danger",
  neutral: "text-text-muted",
};

/**
 * Big bold hero number with a muted label - the KPI stat tier of the type
 * scale. The value is set in tabular-nums so a row of these lines up.
 */
export function KpiStat({ label, value, delta, deltaTone = "neutral", icon, className }: KpiStatProps) {
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-text-muted">
          {label}
        </span>
        {icon && <span className="text-text-muted">{icon}</span>}
      </div>
      <span className="text-4xl sm:text-5xl font-extrabold tracking-tight tabular-nums text-text">
        {value}
      </span>
      {delta && (
        <span className={cn("text-xs font-medium tabular-nums", deltaToneClass[deltaTone])}>
          {delta}
        </span>
      )}
    </div>
  );
}
