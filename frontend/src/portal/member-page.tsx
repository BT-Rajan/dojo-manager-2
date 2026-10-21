import { useQuery } from "@tanstack/react-query";
import { Link } from "wouter";
import { portalApi, type FamilyMember } from "./api";
import { portalDate, useLang } from "./i18n";

/** One member's page: membership, classes, progress, receipts, photos and rules. */
export function MemberPage({ id }: { id: number }) {
  const { t } = useLang();
  const { data: family, isLoading } = useQuery<FamilyMember[]>({
    queryKey: ["/api/portal/family"],
    queryFn: () => portalApi<FamilyMember[]>("/api/portal/family"),
  });
  const row = family?.find((m) => m.id === id);
  if (isLoading) return <p className="ea-meta ea-block">{t("Loading…", "جارٍ التحميل…")}</p>;
  if (!row) return <NotInFamily />;
  const m = row.membership;
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
              {row.first_name} {row.last_name}
            </h1>
            <p className="ea-lead">{row.branch_name}</p>
          </div>
        </div>
      </section>
      <section className="ea-block">
        <div className="ea-wrap ea-stack">
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
                  <div className={row.expiring ? "is-warn" : undefined}>
                    <span>{t("Valid until", "صالح حتى")}</span>
                    <b>
                      {portalDate(m.end_date)}
                      {row.status === "frozen" && ` · ${t("frozen", "مجمّد")}`}
                    </b>
                  </div>
                </div>
              ) : (
                <p className="ea-meta">{t("No membership yet.", "لا يوجد اشتراك بعد.")}</p>
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
