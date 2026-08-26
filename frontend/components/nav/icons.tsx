import type { SVGProps } from "react";

/**
 * Small inline icon set for PillNav's placeholder items. No icon-library
 * dependency exists in the project yet, so plain inline SVGs keep this
 * self-contained until a real icon set is chosen.
 */
function IconBase(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      width={20}
      height={20}
      aria-hidden="true"
      {...props}
    />
  );
}

export function UploadIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <IconBase {...props}>
      <path d="M12 16V4" />
      <path d="M6 10l6-6 6 6" />
      <path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" />
    </IconBase>
  );
}

export function ReviewIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <IconBase {...props}>
      <rect x="3" y="4" width="8" height="16" rx="2" />
      <rect x="13" y="4" width="8" height="16" rx="2" />
      <path d="M6 9h2M6 13h2M15 9h2M15 13h2" />
    </IconBase>
  );
}

export function ExceptionsIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <IconBase {...props}>
      <path d="M12 3l9 16H3l9-16z" />
      <path d="M12 10v4" />
      <path d="M12 17.5v.01" />
    </IconBase>
  );
}

export function ExportIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <IconBase {...props}>
      <path d="M12 4v12" />
      <path d="M18 10l-6-6-6 6" />
      <path d="M4 20h16" />
    </IconBase>
  );
}
