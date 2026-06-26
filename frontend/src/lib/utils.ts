import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Safe ISO/date parse → epoch ms, or null if missing/invalid. */
export function safeParseDate(dateStr: string | null | undefined): number | null {
  if (!dateStr) return null;
  const t = new Date(dateStr).getTime();
  return isFinite(t) ? t : null;
}

/**
 * Display label for VB FAD/DOF cells.
 * Distinguishes Current ("C") vs Unavailable ("U") when status is provided;
 * null date without status falls back to "Current" for backward compatibility.
 */
export function formatVbCutoff(
  dateStr: string | null | undefined,
  status?: string | null,
  opts?: { month?: "short" | "long"; unavailableLabel?: string; currentLabel?: string },
): string {
  const unavailableLabel = opts?.unavailableLabel ?? "Unavailable";
  const currentLabel = opts?.currentLabel ?? "Current";
  if (status === "U" || status === "Unavailable") return unavailableLabel;
  if (!dateStr) {
    if (status === "C" || status === "Current" || !status) return currentLabel;
    return currentLabel;
  }
  const d = new Date(dateStr);
  if (!isFinite(d.getTime())) return currentLabel;
  return d.toLocaleDateString(undefined, {
    month: opts?.month ?? "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** Format an ISO date for charts/labels; returns fallback if null/invalid. */
export function formatIsoDate(
  dateStr: string | null | undefined,
  fallback = "—",
  opts?: Intl.DateTimeFormatOptions,
): string {
  if (!dateStr) return fallback;
  const d = new Date(dateStr);
  if (!isFinite(d.getTime())) return fallback;
  return d.toLocaleDateString(undefined, {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
    ...opts,
  });
}
