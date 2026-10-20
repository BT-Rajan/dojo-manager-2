// Display rules: dates DD-MM-YYYY, times HH:mm:ss (24-hour), everything in Kuwait time
// regardless of the browser's own time zone. The API itself exchanges ISO 8601 values.

export const ACADEMY_TZ = "Asia/Kuwait";

export const WEEKDAYS = ["", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

const pad = (n: number) => String(n).padStart(2, "0");

/** Kuwaiti dinar, 3 decimals. */
export function kd(value: string | number | null | undefined): string {
  const n = typeof value === "string" ? Number(value) : (value ?? 0);
  return `${n.toLocaleString("en-US", { minimumFractionDigits: 3, maximumFractionDigits: 3 })} KD`;
}

/** "2026-10-20" -> "20-10-2026". Calendar dates carry no time zone, so no conversion. */
export function fmtDate(value: string | null | undefined): string {
  if (!value) return "—";
  const [y, m, d] = value.slice(0, 10).split("-");
  return `${d}-${m}-${y}`;
}

const tsParts = new Intl.DateTimeFormat("en-GB", {
  timeZone: ACADEMY_TZ,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

/** API timestamp (ISO with offset) -> "20-10-2026 16:56:00" in Kuwait time. */
export function fmtDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const p = Object.fromEntries(tsParts.formatToParts(new Date(value)).map((x) => [x.type, x.value]));
  return `${p.day}-${p.month}-${p.year} ${p.hour}:${p.minute}:${p.second}`;
}

/** Wall-clock class time "16:30" or "16:30:00" -> "16:30:00". */
export function fmtTime(value: string): string {
  return value.length === 5 ? `${value}:00` : value.slice(0, 8);
}

/** Today's calendar date in Kuwait, as a local Date at midnight (for date arithmetic). */
export function academyToday(): Date {
  const p = Object.fromEntries(tsParts.formatToParts(new Date()).map((x) => [x.type, x.value]));
  return new Date(Number(p.year), Number(p.month) - 1, Number(p.day));
}

/** Calendar Date -> "2026-10-20" for the API. Defaults to today in Kuwait. */
export function isoDate(d: Date = academyToday()): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Calendar Date -> "20-10-2026". */
export function dmy(d: Date): string {
  return fmtDate(isoDate(d));
}

/** "2026-10-17" -> "Saturday 17-10-2026" */
export function fmtDay(value: string): string {
  const [y, m, d] = value.split("-").map(Number);
  const weekday = new Date(y, m - 1, d).getDay(); // 0 = Sunday
  return `${WEEKDAYS[weekday === 0 ? 7 : weekday]} ${fmtDate(value)}`;
}

/** "20-10-2026" -> "2026-10-20", or null when not a real date. */
export function parseDmy(text: string): string | null {
  const m = /^(\d{2})-(\d{2})-(\d{4})$/.exec(text.trim());
  if (!m) return null;
  const [, d, mo, y] = m.map(Number);
  const dt = new Date(y, mo - 1, d);
  if (dt.getFullYear() !== y || dt.getMonth() !== mo - 1 || dt.getDate() !== d) return null;
  return `${m[3]}-${m[2]}-${m[1]}`;
}

/** "16:30:00" (or "16:30") -> "16:30:00", or null when invalid. */
export function parseHms(text: string): string | null {
  const m = /^([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?$/.exec(text.trim());
  return m ? `${m[1]}:${m[2]}:${m[3] ?? "00"}` : null;
}

/** Current Kuwait wall-clock time "HH:mm:ss". */
export function academyNow(): string {
  const p = Object.fromEntries(tsParts.formatToParts(new Date()).map((x) => [x.type, x.value]));
  return `${p.hour}:${p.minute}:${p.second}`;
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
