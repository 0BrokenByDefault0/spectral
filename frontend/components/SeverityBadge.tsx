import type { Severity } from "@/lib/types";

/**
 * Severity is never carried by colour alone: the three levels are all warm and two of
 * them are close enough to be hard to separate by eye, so each badge also states the
 * word and uses a different fill weight.
 */
const STYLES: Record<Severity, string> = {
  MINOR: "border-minor text-minor",
  MODERATE: "border-moderate bg-moderate/15 text-moderate",
  CRITICAL: "border-critical bg-critical text-black",
};

const LABELS: Record<Severity, string> = {
  MINOR: "Minor",
  MODERATE: "Moderate",
  CRITICAL: "Critical",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span
      className={`inline-flex shrink-0 rounded border px-2 py-0.5 text-xs font-medium uppercase tracking-wide ${STYLES[severity]}`}
    >
      {LABELS[severity]}
    </span>
  );
}
