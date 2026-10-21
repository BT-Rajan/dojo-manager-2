import { useQuery } from "@tanstack/react-query";
import { Route, Switch } from "wouter";
import { PortalError, portalApi, type PortalMe } from "./api";
import { AccountPage } from "./account";
import { FamilyPage } from "./family";
import { useLang } from "./i18n";
import { MemberPage, NotInFamily } from "./member-page";
import { PortalShell } from "./shell";
import { SignIn } from "./sign-in";

/**
 * The member and parent portal at /portal. It has its own sign-in (mobile + WhatsApp code)
 * and its own session cookie; nothing here uses the staff login.
 */
export default function PortalApp() {
  const { t } = useLang();
  const { data: me, isLoading } = useQuery<PortalMe | null>({
    queryKey: ["/api/portal/me"],
    queryFn: async () => {
      try {
        return await portalApi<PortalMe>("/api/portal/me");
      } catch (e) {
        if (e instanceof PortalError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 5 * 60_000,
  });

  if (isLoading) {
    return (
      <PortalShell title={t("Member portal", "بوابة الأعضاء")}>
        <p className="ea-meta ea-block" role="status">
          {t("Loading…", "جارٍ التحميل…")}
        </p>
      </PortalShell>
    );
  }
  if (!me) {
    return (
      <PortalShell title={t("Sign in", "تسجيل الدخول")}>
        <SignIn />
      </PortalShell>
    );
  }
  return (
    <Switch>
      <Route path="/portal/member/:id">
        {(p) => (
          <PortalShell title={t("Member portal", "بوابة الأعضاء")}>
            <MemberPage id={Number(p.id)} />
          </PortalShell>
        )}
      </Route>
      <Route path="/portal/account">
        <PortalShell title={t("Account and messages", "الحساب والرسائل")}>
          <AccountPage me={me} />
        </PortalShell>
      </Route>
      <Route path="/portal">
        <PortalShell title={t("Member portal", "بوابة الأعضاء")}>
          <FamilyPage me={me} />
        </PortalShell>
      </Route>
      <Route>
        <PortalShell title={t("Member portal", "بوابة الأعضاء")}>
          <NotInFamily />
        </PortalShell>
      </Route>
    </Switch>
  );
}
