import { useEffect, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "wouter";
import { portalApi, type Account, type PortalMe } from "./api";
import { portalDate, useLang } from "./i18n";
import { Notes } from "./ui";

/** Account and messages: the family, the sign-in mobile, email, WhatsApp choices and the
 * messages the academy sent recently. */
export function AccountPage({ me }: { me: PortalMe }) {
  const { t, lang } = useLang();
  const qc = useQueryClient();
  const { data } = useQuery<Account>({ queryKey: ["/api/portal/account"], queryFn: () => portalApi<Account>("/api/portal/account") });
  const [f, setF] = useState({ email: "", service: true, broadcasts: false });
  const [notes, setNotes] = useState<{ kind: "success" | "error"; text: string }[]>([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (data) setF({ email: data.email ?? "", service: data.service_on, broadcasts: data.broadcasts_on });
  }, [data]);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await portalApi<Account>("/api/portal/account", {
        method: "POST",
        body: { email: f.email.trim() || null, service: f.service, broadcasts: f.broadcasts, lang },
      });
      qc.setQueryData(["/api/portal/account"], r);
      setNotes([{ kind: "success", text: t("Saved.", "تم الحفظ.") }]);
    } catch (err) {
      setNotes([{ kind: "error", text: err instanceof Error ? err.message : String(err) }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <section className="ea-band">
        <div className="ea-band-in">
          <div style={{ display: "grid", gap: 10 }}>
            <p className="ea-eyebrow">
              <Link href="/portal" style={{ textDecoration: "underline" }}>
                {t("Member portal", "بوابة الأعضاء")}
              </Link>
            </p>
            <h1 className="ea-h1">{t("Account and messages", "الحساب والرسائل")}</h1>
          </div>
        </div>
      </section>
      <section className="ea-block">
        <div className="ea-wrap ea-wrap--mid ea-stack">
          <Notes notes={notes} />
          <section className="ea-card" aria-labelledby="h-fam">
            <div className="ea-card-body" style={{ display: "grid", gap: 8 }}>
              <h2 className="ea-h3" id="h-fam">
                {t("Family", "العائلة")}
              </h2>
              {!data || data.family.length === 0 ? (
                <p className="ea-meta">—</p>
              ) : (
                data.family.map((m) => (
                  <Link key={m.id} href={`/portal/member/${m.id}`}>
                    {lang === "ar" && m.first_name_ar ? `${m.first_name_ar} ${m.last_name_ar ?? ""}` : `${m.first_name} ${m.last_name}`}
                  </Link>
                ))
              )}
            </div>
          </section>
          <form className="ea-card ea-form" onSubmit={save}>
            <div className="ea-card-body" style={{ display: "grid", gap: 12 }}>
              <h2 className="ea-h3">{t("Details and messages", "البيانات والرسائل")}</h2>
              <p className="ea-meta">
                {t("Mobile (your sign-in)", "الجوال (للدخول)")}: <span dir="ltr">{me.mobile}</span> ·{" "}
                {t("to change it, contact the branch.", "لتغييره تواصل مع الفرع.")}
              </p>
              <div className="ea-field">
                <label className="ea-label" htmlFor="em">
                  {t("Email", "البريد الإلكتروني")}
                </label>
                <input className="ea-input" id="em" type="email" dir="ltr" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
              </div>
              <fieldset className="ea-field" style={{ gap: 6 }}>
                <legend className="ea-label">{t("WhatsApp messages", "رسائل واتساب")}</legend>
                <p className="ea-hint" style={{ margin: 0 }}>
                  {t(
                    "Receipts, sign-in codes, trial and class-change messages are always sent.",
                    "الإيصالات ورموز الدخول ورسائل التجربة وتغيير الحصص تُرسل دائماً.",
                  )}
                </p>
                <label className="ea-check">
                  <input type="checkbox" checked={f.service} onChange={(e) => setF({ ...f, service: e.target.checked })} />{" "}
                  {t("Reminders, test days and progress notes", "التذكيرات وأيام الاختبار وتقارير التقدم")}
                </label>
                <label className="ea-check">
                  <input type="checkbox" checked={f.broadcasts} onChange={(e) => setF({ ...f, broadcasts: e.target.checked })} />{" "}
                  {t("News and offers from the academy", "أخبار وعروض الأكاديمية")}
                </label>
              </fieldset>
              <button className="ea-btn ea-btn--primary" disabled={busy || !data}>
                {t("Save", "حفظ")}
              </button>
            </div>
          </form>
          <section className="ea-card" aria-labelledby="h-msg">
            <div className="ea-card-body" style={{ display: "grid", gap: 8 }}>
              <h2 className="ea-h3" id="h-msg">
                {t("Recent messages", "الرسائل الأخيرة")}
              </h2>
              {!data || data.recent.length === 0 ? (
                <p className="ea-meta">—</p>
              ) : (
                data.recent.map((m, i) => (
                  <div key={i}>
                    <p className="ea-meta">{portalDate(m.at)}</p>
                    <p dir="auto" style={{ whiteSpace: "pre-line", margin: 0 }}>
                      {m.text}
                    </p>
                  </div>
                ))
              )}
            </div>
          </section>
        </div>
      </section>
    </>
  );
}
