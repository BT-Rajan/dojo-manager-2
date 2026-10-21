import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "wouter";
import { portalApi, type FamilyMember, type PortalMe } from "./api";
import { ar, clock, portalDate, useLang } from "./i18n";
import { AlertIcon, Band, BeltBar, Belt, Illo, Rank, branchKey } from "./ui";

function ChildCard({ row }: { row: FamilyMember }) {
  const { t, lang } = useLang();
  const first = ar(lang, row.first_name, row.first_name_ar);
  const n = row.next_class;
  const m = row.membership;
  return (
    <article className="ea-card" data-branch={branchKey(row.branch_code)}>
      <div className="ea-card-body ea-child">
        <div className="ea-child-head">
          <span className="ea-avatar" aria-hidden="true">
            {first.slice(0, 1)}
          </span>
          <div style={{ flex: 1 }}>
            <h2 className="ea-h3" style={{ fontSize: 20, lineHeight: "28px" }}>
              {first}
            </h2>
            <span className="ea-meta" style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
              <i className="ea-branchdot" />
              {ar(lang, row.branch_name, row.branch_name_ar)}
            </span>
          </div>
        </div>
        {row.rank && (
          <div style={{ display: "grid", gap: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <Rank belt={row.rank.belt} />
              {row.rank.next_belt && (
                <span className="ea-meta" style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                  {t("Next:", "التالي:")} <Belt color={row.rank.next_belt.color} width={24} />
                  {row.rank.next_belt.name}
                </span>
              )}
            </div>
            <div className="ea-progress" role="img" aria-label={`${row.rank.stripes}/4`}>
              {[0, 1, 2, 3].map((i) => (
                <i key={i} className={i < row.rank!.stripes ? "on" : undefined} />
              ))}
            </div>
            <span className="ea-meta">
              <span dir="ltr">{row.rank.stripes}/4</span> {t("stripes", "أشرطة")}
            </span>
          </div>
        )}
        <div className="ea-kv">
          <div>
            <span>{t("Next class", "الحصة القادمة")}</span>
            <b>{n ? `${portalDate(n.session_date)} · ${clock(n.start_time)} · ${ar(lang, n.title, n.title_ar)}` : "—"}</b>
          </div>
          <div className={row.expiring ? "is-warn" : undefined}>
            <span>{t("Membership until", "الاشتراك حتى")}</span>
            <b>
              {m ? portalDate(m.end_date) : "—"}
              {row.status === "frozen" && ` · ${t("frozen", "مجمّد")}`}
              {row.expiring && (
                <>
                  {" · "}
                  <span style={{ display: "inline-flex", verticalAlign: "middle" }}>
                    <AlertIcon />
                  </span>{" "}
                  {row.status === "expired" ? t("ended — renew", "انتهى — جدّد") : t("renew soon", "جدّد قريباً")}
                </>
              )}
            </b>
          </div>
        </div>
        <div className="ea-btnrow">
          <Link className={`ea-btn ${row.expiring ? "ea-btn--primary" : "ea-btn--ghost"}`} href={`/portal/member/${row.id}`}>
            {row.expiring ? t("Renew and more", "جدّد والمزيد") : t("Classes, progress and receipts", "الحصص والتقدم والإيصالات")}
            <span className="ea-sr"> · {first}</span>
          </Link>
        </div>
      </div>
    </article>
  );
}

/** The signed-in family: one card per child (or the adult member). */
export function FamilyPage({ me }: { me: PortalMe }) {
  const { t, lang } = useLang();
  const qc = useQueryClient();
  const { data: family, isLoading } = useQuery<FamilyMember[]>({
    queryKey: ["/api/portal/family"],
    queryFn: () => portalApi<FamilyMember[]>("/api/portal/family"),
  });
  const signOut = async () => {
    await portalApi("/api/portal/logout", { method: "POST" }).catch(() => undefined);
    qc.removeQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("/api/portal") });
    await qc.invalidateQueries({ queryKey: ["/api/portal/me"] });
  };
  return (
    <>
      <Band
        eyebrow={t("Member portal", "بوابة الأعضاء")}
        title={lang === "ar" ? `أهلاً ${me.name_ar ?? me.name}` : `Hello${me.name ? `, ${me.name}` : ""}`}
        lead={t("Your family's belts, classes, renewals and receipts.", "أحزمة عائلتك وحصصهم وتجديداتهم وإيصالاتهم.")}
      />
      <BeltBar />
      <section className="ea-block">
        <div className="ea-wrap">
          {isLoading ? (
            <p className="ea-meta" role="status">
              {t("Loading…", "جارٍ التحميل…")}
            </p>
          ) : family && family.length > 0 ? (
            <div className="ea-portal-grid">
              {family.map((row) => (
                <ChildCard key={row.id} row={row} />
              ))}
            </div>
          ) : (
            <div className="ea-empty">
              <Illo />
              <p className="ea-h4">{t("We couldn't find any active memberships on this number", "لم نجد اشتراكات فعّالة على هذا الرقم")}</p>
              <p className="ea-meta">{t("WhatsApp your branch and we'll link your family to your number.", "راسل فرعك عبر واتساب وسنربط عائلتك برقمك.")}</p>
            </div>
          )}
          <div className="ea-btnrow" style={{ marginBlockStart: 32 }}>
            <Link className="ea-btn ea-btn--ghost" href="/portal/account">
              {t("Account and messages", "الحساب والرسائل")}
            </Link>
            <button type="button" className="ea-btn ea-btn--ghost" onClick={() => void signOut()}>
              {t("Sign out", "تسجيل الخروج")}
            </button>
          </div>
        </div>
      </section>
    </>
  );
}
