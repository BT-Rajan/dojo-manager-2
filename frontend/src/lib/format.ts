import { format, parseISO } from "date-fns";

export const WEEKDAYS = ["", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

/** Kuwaiti dinar, 3 decimals. */
export function kd(value: string | number | null | undefined): string {
  const n = typeof value === "string" ? Number(value) : (value ?? 0);
  return `${n.toLocaleString("en-US", { minimumFractionDigits: 3, maximumFractionDigits: 3 })} KD`;
}

export function fmtDate(value: string | null | undefined): string {
  return value ? format(parseISO(value), "dd MMM yyyy") : "—";
}

export function fmtDateTime(value: string | null | undefined): string {
  // API timestamps are UTC without a zone suffix.
  return value ? format(new Date(value.endsWith("Z") ? value : `${value}Z`), "dd MMM yyyy HH:mm") : "—";
}

export function fmtTime(value: string): string {
  return value.slice(0, 5);
}

export function isoDate(d: Date = new Date()): string {
  return format(d, "yyyy-MM-dd");
}

export function label(value: string | null | undefined): string {
  if (!value) return "—";
  return value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export const ROLE_LABELS: Record<string, string> = {
  owner: "Owner",
  manager: "Operations Manager",
  branch_admin: "Branch Admin",
  instructor: "Instructor",
};
