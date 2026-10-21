import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "wouter";
import { portalApi, type MemberDetail } from "./api";
import { clock, dayLabel, portalDate, useLang } from "./i18n";
import { Notes } from "./ui";

type Note = { kind: "success" | "error"; text: string };

/** One member's page: membership, classes this week, progress, receipts, photos and rules. */
export function MemberPage({ id }: { id: number }) {
  const { t, lang } = useLang();
  const qc = useQueryClient();
  const url = `/api/portal/members/${id}`;
  const { data, isLoading, error } = useQuery<MemberDetail>({ queryKey: [url], queryFn: () => portalApi<MemberDetail>(url) });
  const [notes, setNotes] = useState<Note[]>([]);
  const [busy, setBusy] = useState(false);

  /** Run a portal action, then show its result above the page as the website does. */
  const act = async (fn: () => Promise<Note>) => {
    setBusy(true);
    try {
      setNotes([await fn()]);
    } catch (e) {
      setNotes([{ kind: "error", text: e instanceof Error ? e.message : String(e) }]);
    } finally {
      setBusy(false);
      await qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("/api/portal/") && q.queryKey[0] !== "/api/portal/me" });
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  };
  const book = (sessionId: number) =>
    act(async () => {
      const r = await portalApi<{ status: string }>(`${url}/book`, { method: "POST", body: { session_id: sessionId, lang } });
      return {
        kind: "success",
        text: r.status === "waitlisted" ? t("On the waiting list — we'll message you.", "في قائمة الانتظار — سنراسلك.") : t("Booked.", "تم الحجز."),
      };
    });
  const cancel = (sessionId: number) =>
    act(async () => {
      const r = await portalApi<{ late_cancellation: boolean }>(`${url}/cancel`, { method: "POST", body: { session_id: sessionId, lang } });
      return {
        kind: "success",
        text: r.late_cancellation
          ? t("Cancelled (less than 2 hours' notice is noted).", "تم الإلغاء (يُسجَّل الإلغاء قبل أقل من ساعتين).")
          : t("Cancelled.", "تم الإلغاء."),
      };
    });

  if (isLoading) return <p className="ea-meta ea-block">{t("Loading…", "جارٍ التحميل…")}</p>;
  if (!data || error) return <NotInFamily />;
  const { member, membership: m, status } = data;
  const warn = status === "expiring" || status === "expired";

  return (
    <>
      <section className="ea-band">
        <div className="ea-band-in">
          <div style={{ display: "grid", gap: 10 }}>
            <p className="ea-eyebrow">
              <Link href="/portal" style={{ textDecoration: "underline" }}>
                {t("Member portal", "بوابة الأعضاء")}
              </Link>
              {" · "}
              <Link href="/portal/account" style={{ textDecoration: "underline" }}>
                {t("Account and messages", "الحساب والرسائل")}
              </Link>
            </p>
            <h1 className="ea-h1">
              {member.first_name} {member.last_name}
            </h1>
            <p className="ea-lead">{member.branch_name}</p>
          </div>
        </div>
      </section>
      <section className="ea-block">
        <div className="ea-wrap ea-stack">
          <Notes notes={notes} />
          <section className="ea-card" aria-labelledby="h-mem">
            <div className="ea-card-body" style={{ display: "grid", gap: 12 }}>
              <h2 className="ea-h3" id="h-mem">
                {t("Membership", "الاشتراك")}
              </h2>
              {m ? (
                <div className="ea-kv">
                  <div>
                    <span>{t("Plan", "الخطة")}</span>
                    <b>{m.plan_name}</b>
                  </div>
                  <div className={warn ? "is-warn" : undefined}>
                    <span>{t("Valid until", "صالح حتى")}</span>
                    <b>
                      {portalDate(m.end_date)}
                      {status === "frozen" && ` · ${t("frozen", "مجمّد")}`}
                    </b>
                  </div>
                </div>
              ) : (
                <p className="ea-meta">{t("No membership yet.", "لا يوجد اشتراك بعد.")}</p>
              )}
            </div>
          </section>

          <section className="ea-card" aria-labelledby="h-cls">
            <div className="ea-card-body" style={{ display: "grid", gap: 12 }}>
              <h2 className="ea-h3" id="h-cls">
                {t("Classes this week", "حصص هذا الأسبوع")}
              </h2>
              {data.classes.length === 0 ? (
                <p className="ea-meta">{t("No classes to show this week.", "لا توجد حصص هذا الأسبوع.")}</p>
              ) : (
                <div>
                  {data.classes.map((r) => (
                    <div key={r.session_id} className="ea-row">
                      <span>
                        {dayLabel(r.session_date, lang)} · <span dir="ltr">{clock(r.start_time)}</span> · {r.title}
                      </span>
                      {r.regular ? (
                        <span className="ea-meta">{t("Regular class", "حصة منتظمة")}</span>
                      ) : r.booking ? (
                        <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
                          <span className="ea-meta">
                            {r.booking.status === "waitlisted" ? t("Waiting list", "قائمة الانتظار") : t("Booked", "محجوز")}
                          </span>
                          <button type="button" className="ea-btn ea-btn--ghost ea-btn--sm" disabled={busy} onClick={() => void cancel(r.session_id)}>
                            {t("Cancel", "إلغاء")}
                          </button>
                        </span>
                      ) : r.can_book ? (
                        <button type="button" className="ea-btn ea-btn--primary ea-btn--sm" disabled={busy} onClick={() => void book(r.session_id)}>
                          {t("Book", "احجز")}
                        </button>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}
              {data.attendance.length > 0 && (
                <details>
                  <summary className="ea-meta">{t("Recent attendance", "الحضور الأخير")}</summary>
                  <ul style={{ margin: "8px 0 0", paddingInlineStart: 20 }}>
                    {data.attendance.map((a, i) => (
                      <li key={i}>
                        {portalDate(a.session_date)} · {a.title}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          </section>
        </div>
      </section>
    </>
  );
}

export function NotInFamily() {
  const { t } = useLang();
  return (
    <section className="ea-block">
      <div className="ea-wrap ea-wrap--mid">
        <div className="ea-empty">
          <p className="ea-h4">{t("This page isn't part of your family's portal.", "هذه الصفحة ليست ضمن بوابة عائلتك.")}</p>
          <Link className="ea-btn ea-btn--ghost" href="/portal">
            {t("Back to the member portal", "العودة إلى بوابة الأعضاء")}
          </Link>
        </div>
      </div>
    </section>
  );
}
