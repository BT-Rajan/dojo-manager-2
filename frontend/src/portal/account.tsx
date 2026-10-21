import { useQuery } from "@tanstack/react-query";
import { Link } from "wouter";
import { portalApi, type FamilyMember, type PortalMe } from "./api";
import { useLang } from "./i18n";

/** Account and messages: the family, the sign-in mobile, details and message choices. */
export function AccountPage({ me }: { me: PortalMe }) {
  const { t } = useLang();
  const { data: family = [] } = useQuery<FamilyMember[]>({
    queryKey: ["/api/portal/family"],
    queryFn: () => portalApi<FamilyMember[]>("/api/portal/family"),
  });
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
          <section className="ea-card" aria-labelledby="h-fam">
            <div className="ea-card-body" style={{ display: "grid", gap: 8 }}>
              <h2 className="ea-h3" id="h-fam">
                {t("Family", "العائلة")}
              </h2>
              {family.length === 0 ? (
                <p className="ea-meta">—</p>
              ) : (
                family.map((m) => (
                  <Link key={m.id} href={`/portal/member/${m.id}`}>
                    {m.first_name} {m.last_name}
                  </Link>
                ))
              )}
            </div>
          </section>
          <section className="ea-card">
            <div className="ea-card-body" style={{ display: "grid", gap: 12 }}>
              <h2 className="ea-h3">{t("Details and messages", "البيانات والرسائل")}</h2>
              <p className="ea-meta">
                {t("Mobile (your sign-in)", "الجوال (للدخول)")}: <span dir="ltr">{me.mobile}</span> ·{" "}
                {t("to change it, contact the branch.", "لتغييره تواصل مع الفرع.")}
              </p>
            </div>
          </section>
        </div>
      </section>
    </>
  );
}
