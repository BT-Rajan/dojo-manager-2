import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocation } from "wouter";
import { portalApi, type Renewal } from "./api";
import { kd, useLang } from "./i18n";
import { NotInFamily } from "./member-page";

/**
 * The payment page. Until a KNET / card provider is connected this is the test gateway: an
 * Approve and a Decline button in place of the bank's page. No money moves.
 */
export function PaymentPage({ reference }: { reference: string }) {
  const { t, lang } = useLang();
  const url = `/api/portal/renewals/${reference}`;
  const { data, isLoading } = useQuery<Renewal>({ queryKey: [url], queryFn: () => portalApi<Renewal>(url) });
  if (isLoading) return <p className="ea-meta ea-block">{t("Loading…", "جارٍ التحميل…")}</p>;
  if (!data) return <NotInFamily />;
  const back = (outcome: string, sig: string) => `/portal/renewal/${reference}?outcome=${outcome}&sig=${sig}`;
  return (
    <>
      <div className="ea-testmode" role="note" style={{ borderRadius: 0 }}>
        {t(
          "TEST MODE — no bank is connected and no money moves. The real KNET / card provider is chosen before launch.",
          "وضع تجريبي — لا يوجد بنك متصل ولا تتم أي عملية دفع حقيقية. يتم اختيار مزوّد كي نت والبطاقات قبل الإطلاق.",
        )}
      </div>
      <section className="ea-block">
        <div className="ea-wrap" style={{ maxWidth: 480, display: "grid", gap: 20 }}>
          <h1 className="ea-h1">{data.method === "knet" ? "KNET" : "Visa / Mastercard"}</h1>
          <div className="ea-card">
            <div className="ea-card-body">
              <div className="ea-kv">
                <div>
                  <span>{t("Order", "الطلب")}</span>
                  <b dir="ltr">{data.reference}</b>
                </div>
                <div>
                  <span>{t("Amount", "المبلغ")}</span>
                  <b>{kd(data.amount, lang)}</b>
                </div>
              </div>
              <p className="ea-meta">{data.plan_name}</p>
            </div>
          </div>
          {data.test_outcomes ? (
            <>
              <a className="ea-btn ea-btn--primary ea-btn--block" href={back("approve", data.test_outcomes.approve)}>
                {t("Approve payment", "الموافقة على الدفع")}
              </a>
              <a className="ea-btn ea-btn--ghost ea-btn--block" href={back("decline", data.test_outcomes.decline)}>
                {t("Decline (test a failed payment)", "رفض (تجربة دفع فاشل)")}
              </a>
            </>
          ) : (
            <a className="ea-btn ea-btn--ghost ea-btn--block" href={`/portal/member/${data.member_id}`}>
              {t("Back to the member page", "العودة إلى صفحة العضو")}
            </a>
          )}
        </div>
      </section>
    </>
  );
}

/** Back from the payment page: record the answer, then return to the member's page. */
export function RenewalReturn({ reference }: { reference: string }) {
  const { t, lang } = useLang();
  const [, navigate] = useLocation();
  const qc = useQueryClient();
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    portalApi<Renewal>(`/api/portal/renewals/${reference}/complete`, {
      method: "POST",
      body: { outcome: q.get("outcome") ?? "", sig: q.get("sig") ?? "", lang },
    })
      .then(async (r) => {
        await qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("/api/portal/") });
        navigate(`/portal/member/${r.member_id}?renewal=${r.status === "paid" ? "paid" : "failed"}`, { replace: true });
      })
      .catch(() => setFailed(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reference]);
  if (failed) return <NotInFamily />;
  return (
    <p className="ea-meta ea-block" role="status">
      {t("Checking the payment…", "جارٍ التحقق من الدفع…")}
    </p>
  );
}
