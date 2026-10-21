import type { CSSProperties, ReactNode } from "react";
import { setLang, useLang } from "./i18n";
import type { BeltBrief } from "./api";

const BAR = [
  ["white", "#ffffff"],
  ["yellow", "#f4c430"],
  ["purple", "#6a3fa0"],
  ["blue", "#1f4fa8"],
  ["green", "#2e7d32"],
  ["brown", "#7a4b25"],
  ["brownblack", "#7a4b25"],
  ["black", "#1a1a1a"],
] as const;

/** The belt-colour strip under the band, as on the academy website. */
export function BeltBar() {
  return (
    <div className="ea-beltbar" aria-hidden="true">
      {BAR.map(([k, c]) => (
        <i key={k} data-belt={k} style={{ "--belt-c": c } as CSSProperties} />
      ))}
    </div>
  );
}

function isLight(hex: string): boolean {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!m) return false;
  const n = parseInt(m[1], 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  return 0.299 * r + 0.587 * g + 0.114 * b > 220;
}

export function Belt({ color, width }: { color: string; width?: number }) {
  return (
    <span
      className="ea-belt"
      data-light={isLight(color) ? "1" : undefined}
      style={{ "--belt-c": color, ...(width ? { width } : {}) } as CSSProperties}
      aria-hidden="true"
    />
  );
}

export function Rank({ belt }: { belt: BeltBrief }) {
  return (
    <span className="ea-rank">
      <Belt color={belt.color} />
      {belt.name}
    </span>
  );
}

/** Green-belt eyebrow over page titles ("Member portal"). */
export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <p className="ea-eyebrow">
      <Belt color="#2e7d32" />
      {children}
    </p>
  );
}

export function Band({ eyebrow, title, lead }: { eyebrow: ReactNode; title: ReactNode; lead?: ReactNode }) {
  return (
    <section className="ea-band">
      <div className="ea-band-in">
        <div style={{ display: "grid", gap: 10 }}>
          <Eyebrow>{eyebrow}</Eyebrow>
          <h1 className="ea-h1">{title}</h1>
          {lead && <p className="ea-lead">{lead}</p>}
        </div>
      </div>
    </section>
  );
}

/** Success or error notes after an action, like the website's flash messages. */
export function Notes({ notes }: { notes: { kind: "success" | "error"; text: string }[] }) {
  if (notes.length === 0) return null;
  return (
    <div role="status" style={{ display: "grid", gap: 8 }}>
      {notes.map((n, i) => (
        <div key={i} className={`ea-note ${n.kind === "error" ? "ea-note--warning" : "ea-note--success"}`}>
          {n.text}
        </div>
      ))}
    </div>
  );
}

export function AlertIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <path d="M12 8v5M12 16h.01" />
    </svg>
  );
}

/** Empty-state drawing: a folded belt. */
export function Illo() {
  return (
    <svg viewBox="0 0 120 90" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <rect x="20" y="38" width="80" height="14" rx="4" />
      <path d="M52 52l-10 26M68 52l10 26" />
      <rect x="50" y="34" width="20" height="22" rx="3" />
    </svg>
  );
}

export function branchKey(code: string): string | undefined {
  if (code === "PRM") return "promenade";
  if (code === "BDY") return "bedaya";
  return undefined;
}

export function LangButton() {
  const { lang } = useLang();
  return (
    <button type="button" className="ea-lang" onClick={() => setLang(lang === "ar" ? "en" : "ar")} lang={lang === "ar" ? "en" : "ar"}>
      {lang === "ar" ? "English" : "عربي"}
    </button>
  );
}
