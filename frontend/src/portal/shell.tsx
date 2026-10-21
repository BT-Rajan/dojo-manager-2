import { useEffect, useState, type ReactNode } from "react";
import { Link } from "wouter";
import "./portal.css";
import { useLang } from "./i18n";
import { LangButton } from "./ui";

function useSystemDark() {
  const [dark, setDark] = useState(() => window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false);
  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!mq) return;
    const on = (e: MediaQueryListEvent) => setDark(e.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return dark;
}

/** Page frame for the portal: academy header with language switch, content, footer. */
export function PortalShell({ children, title }: { children: ReactNode; title: string }) {
  const { t, lang, dir } = useLang();
  const dark = useSystemDark();
  useEffect(() => {
    document.title = `${title} · ${t("Elite Academy", "أكاديمية إيليت")}`;
  }, [title, t]);
  return (
    <div className="ea-portal" dir={dir} lang={lang} data-theme={dark ? "dark" : "light"}>
      <a href="#main" className="ea-sr">
        {t("Skip to content", "انتقل إلى المحتوى")}
      </a>
      <header className="ea-header">
        <div className="ea-header-in">
          <Link href="/portal" className="ea-brand">
            <span className="ea-brand-mark" aria-hidden="true">
              E
            </span>
            {t("Elite Academy", "أكاديمية إيليت")}
          </Link>
          <div className="ea-header-end">
            <LangButton />
          </div>
        </div>
      </header>
      <main id="main">{children}</main>
      <footer className="ea-footer">
        <div className="ea-footer-in">
          <span>{t("Elite Academy · Member portal", "أكاديمية إيليت · بوابة الأعضاء")}</span>
          <span>{t("Questions? WhatsApp your branch.", "أسئلة؟ راسل فرعك عبر واتساب.")}</span>
        </div>
      </footer>
    </div>
  );
}
