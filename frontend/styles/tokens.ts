/**
 * Design tokens for the reconciliation tool's visual language.
 *
 * Tailwind v4 uses CSS-first configuration (`@theme` in `app/globals.css`),
 * which is the canonical source that Tailwind reads to generate utility
 * classes (`bg-accent`, `rounded-card`, `shadow-card`, etc). The constants
 * below mirror those same literal values for contexts that need a raw JS
 * value rather than a Tailwind class - inline styles, chart color scales,
 * or non-DOM rendering added in later tasks. Keep the two in sync by hand;
 * there is no build step that generates one from the other.
 */

export const colors = {
  bg: "#F0EFF2",
  surface: "#FFFFFF",
  text: "#000000",
  textMuted: "#5C5C68",
  border: "#E2E1E7",

  accent: "#75FB90",
  accentHover: "#54E278",
  accentActive: "#3ECB66",
  accentSoft: "#E4FCE9",

  // Semantic aliases for confidence bands and exception states. Hue-matched
  // to the mint accent family rather than default Bootstrap red/yellow/green.
  // Variant naming is presentational only - the numeric confidence
  // thresholds that pick a variant belong to the matching engine, not here.
  success: "#167A45",
  successBg: "#DFF5E7",
  warning: "#9A5B0A",
  warningBg: "#FBEEDA",
  danger: "#B7452E",
  dangerBg: "#FBE7E1",
  neutral: "#55555F",
  neutralBg: "#EAE9EE",
} as const;

export const radius = {
  card: "20px",
  pill: "999px",
  sm: "10px",
} as const;

export const shadow = {
  card: "0 1px 2px rgba(15, 15, 20, 0.04), 0 10px 20px -12px rgba(15, 15, 20, 0.10)",
} as const;

/** Standard card interior padding convention. Use `p-6` directly in JSX. */
export const cardPadding = "p-6";

/**
 * Semantic type scale, expressed as Tailwind class strings so every
 * primitive that renders a given role stays visually consistent.
 * `tabular-nums` is included wherever a role renders monetary or numeric
 * figures, so digits stay column-aligned in tables and KPI stacks.
 */
export const textStyles = {
  /** Big bold KPI hero numbers. */
  hero: "text-4xl sm:text-5xl font-extrabold tracking-tight tabular-nums",
  /** Card titles / section headings. */
  title: "text-lg font-semibold tracking-tight",
  /** Default body copy. */
  body: "text-sm font-normal",
  /** Small caption / eyebrow labels (e.g. KPI label, badge text). */
  label: "text-xs font-medium uppercase tracking-wide",
  /** Monetary or numeric table cells - keeps digits aligned. */
  tabularFigure: "tabular-nums",
} as const;
