import { useEffect, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation } from "wouter";
import { portalApi, type MemberDetail } from "./api";
import { clock, dayLabel, kd, portalDate, useLang } from "./i18n";
import { Notes } from "./ui";

const METHOD_LABEL = { knet: "KNET", card: "Visa / Mastercard", cash: { en: "Cash", ar: "نقداً" } };

function localIso(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

type Note = { kind: "success" | "error"; text: string };

/** One member's page: membership, classes this week, progress, receipts, photos and rules. */
export function MemberPage({ id }: { id: number }) {
  const { t, lang } = useLang();
  const qc = useQueryClient();
  const url = `/api/portal/members/${id}`;
  const { data, isLoading, error } = useQuery<MemberDetail>({ queryKey: [url], queryFn: () => portalApi<MemberDetail>(url) });
  const [notes, setNotes] = useState<Note[]>([]);
  const [busy, setBusy] = useState(false);
  const [, navigate] = useLocation();
  const [method, setMethod] = useState<"knet" | "card">("knet");
  const [freeze, setFreeze] = useState({ start: "", weeks: "1", reason: "" });

  // Back from the payment page: show how it went.
  useEffect(() => {
    const result = new URLSearchParams(window.location.search).get("renewal");
    if (result === "paid") setNotes([{ kind: "success", text: t("Payment received — the membership is renewed.", "تم الدفع — تم تجديد الاشتراك.") }]);
    if (result === "failed") setNotes([{ kind: "error", text: t("The payment didn't go through. Nothing was charged.", "لم تتم عملية الدفع. لم يُخصم أي مبلغ.") }]);
    if (result) window.history.replaceState(null, "", window.location.pathname);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  const renew = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await portalApi<{ pay_url: string }>(`${url}/renew`, { method: "POST", body: { method, lang } });
      navigate(r.pay_url);
    } catch (err) {
      setNotes([{ kind: "error", text: err instanceof Error ? err.message : String(err) }]);
      setBusy(false);
    }
  };
  const sendFreeze = (e: FormEvent) => {
    e.preventDefault();
    void act(async () => {
      await portalApi(`${url}/freeze`, {
        method: "POST",
        body: { start_date: freeze.start, weeks: Number(freeze.weeks), reason: freeze.reason, lang },
      });
      return { kind: "success", text: t("Freeze request sent to the branch.", "أُرسل طلب التجميد للفرع.") };
    });
  };

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
              {data.renewal && (
                <form className="ea-form" style={{ gap: 10 }} onSubmit={renew}>
                  <fieldset className="ea-field">
                    <legend className="ea-label">
                      {t("Renew online", "التجديد عبر الإنترنت")} · {kd(data.renewal.price, lang)}
                    </legend>
                    <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                      {(["knet", "card"] as const).map((m) => (
                        <label key={m} className="ea-check">
                          <input type="radio" name="method" value={m} checked={method === m} onChange={() => setMethod(m)} /> {METHOD_LABEL[m]}
                        </label>
                      ))}
                    </div>
                    <span className="ea-hint">
                      {t(
                        "The new period starts the day after the current one ends. Discounts are applied at the branch.",
                        "تبدأ الفترة الجديدة في اليوم التالي لانتهاء الحالية. الخصومات تُطبّق في الفرع.",
                      )}
                    </span>
                  </fieldset>
                  <button className="ea-btn ea-btn--primary" disabled={busy}>
                    {t("Pay and renew", "ادفع وجدّد")}
                  </button>
                </form>
              )}
              {data.freeze && !data.freeze.used &&
                (data.freeze.pending ? (
                  <p className="ea-meta">{t("Freeze request waiting for the branch.", "طلب التجميد بانتظار الفرع.")}</p>
                ) : (
                  <details>
                    <summary className="ea-meta">{t("Request a freeze (1–4 weeks, once per membership)", "طلب تجميد (1–4 أسابيع، مرة لكل اشتراك)")}</summary>
                    <form className="ea-form" style={{ marginBlockStart: 8 }} onSubmit={sendFreeze}>
                      <div className="ea-field">
                        <label className="ea-label" htmlFor="fs">
                          {t("Start", "البداية")}
                        </label>
                        <input
                          className="ea-input"
                          id="fs"
                          type="date"
                          dir="ltr"
                          min={localIso(new Date())}
                          required
                          value={freeze.start}
                          onChange={(e) => setFreeze({ ...freeze, start: e.target.value })}
                        />
                      </div>
                      <div className="ea-field">
                        <label className="ea-label" htmlFor="fw">
                          {t("Weeks", "الأسابيع")}
                        </label>
                        <select className="ea-input" id="fw" value={freeze.weeks} onChange={(e) => setFreeze({ ...freeze, weeks: e.target.value })}>
                          {["1", "2", "3", "4"].map((w) => (
                            <option key={w}>{w}</option>
                          ))}
                        </select>
                      </div>
                      <div className="ea-field">
                        <label className="ea-label" htmlFor="fr">
                          {t("Reason", "السبب")}
                        </label>
                        <input
                          className="ea-input"
                          id="fr"
                          maxLength={200}
                          required
                          value={freeze.reason}
                          onChange={(e) => setFreeze({ ...freeze, reason: e.target.value })}
                        />
                      </div>
                      <button className="ea-btn ea-btn--ghost" disabled={busy || !freeze.start || !freeze.reason.trim()}>
                        {t("Send request", "إرسال الطلب")}
                      </button>
                    </form>
                  </details>
                ))}
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

          {data.receipts.length > 0 && (
            <section className="ea-card" aria-labelledby="h-rc">
              <div className="ea-card-body" style={{ display: "grid", gap: 8 }}>
                <h2 className="ea-h3" id="h-rc">
                  {t("Receipts", "الإيصالات")}
                </h2>
                {data.receipts.map((r) => (
                  <details key={r.reference}>
                    <summary>
                      {portalDate(r.paid_at)} · <span dir="ltr">{r.reference}</span> · {kd(r.amount, lang)}
                    </summary>
                    <ul style={{ margin: "6px 0 0", paddingInlineStart: 20 }}>
                      {r.lines.map((l, i) => (
                        <li key={i}>
                          {l.description} · {kd(l.amount, lang)}
                        </li>
                      ))}
                      <li className="ea-meta">
                        {r.method === "cash" ? METHOD_LABEL.cash[lang] : METHOD_LABEL[r.method]} · {kd(r.amount, lang)}
                      </li>
                    </ul>
                  </details>
                ))}
              </div>
            </section>
          )}
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
