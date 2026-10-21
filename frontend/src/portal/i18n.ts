import { useSyncExternalStore } from "react";

/** Portal language: English or Arabic (right to left), remembered on this device. */
export type Lang = "en" | "ar";

const KEY = "portalLang";
const listeners = new Set<() => void>();

function read(): Lang {
  try {
    return localStorage.getItem(KEY) === "ar" ? "ar" : "en";
  } catch {
    return "en";
  }
}

export function setLang(lang: Lang) {
  try {
    localStorage.setItem(KEY, lang);
  } catch {
    /* storage unavailable */
  }
  listeners.forEach((l) => l());
}

export function useLang() {
  const lang = useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    read,
    () => "en" as Lang,
  );
  /** Pick the text for the current language. */
  const t = (en: string, ar: string) => (lang === "ar" ? ar : en);
  return { lang, t, dir: lang === "ar" ? "rtl" : "ltr" } as const;
}

const pad = (n: number) => String(n).padStart(2, "0");

/** "2026-10-20" -> "20/10/2026" (as the academy writes dates to families). */
export function portalDate(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

/** "17:30:00" -> "17:30". */
export function clock(time: string): string {
  return time.slice(0, 5);
}

const AR_DAYS = ["الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"];
const EN_DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** "2026-10-20" -> "Tue 20/10" / "الثلاثاء 20/10". */
export function dayLabel(iso: string, lang: Lang): string {
  const [y, m, d] = iso.split("-").map(Number);
  const wd = new Date(y, m - 1, d).getDay();
  return `${(lang === "ar" ? AR_DAYS : EN_DAYS)[wd]} ${pad(d)}/${pad(m)}`;
}

/** Kuwaiti dinar, 3 decimals. */
export function kd(value: string | number, lang: Lang): string {
  const n = typeof value === "string" ? Number(value) : value;
  const s = n.toLocaleString("en-US", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
  return lang === "ar" ? `${s} د.ك` : `${s} KD`;
}
