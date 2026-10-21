import { useEffect } from "react";
import { useLocation } from "wouter";
import { Building2, MapPin } from "lucide-react";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { useAuth } from "@/hooks/useAuth";
import { setSelectedBranch, useBranch } from "@/hooks/useBranch";

/** Branch picker. Everything after this is scoped to the chosen branch. */
export default function Home() {
  const { user } = useAuth();
  const { branches, branchId } = useBranch();
  const [, setLocation] = useLocation();
  const active = branches.filter((b) => b.is_active);
  // Coaches land in their own portal; everyone else on the branch dashboard.
  const landing = user?.role === "instructor" ? "/coach" : "/dashboard";

  useEffect(() => {
    if (active.length === 1 && branchId !== active[0].id) {
      setSelectedBranch(active[0].id);
      setLocation(landing);
    }
  }, [active, branchId, landing, setLocation]);

  const choose = (id: number) => {
    setSelectedBranch(id);
    setLocation(landing);
  };

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="max-w-5xl mx-auto px-4 py-10">
        <h2 className="text-2xl font-bold text-foreground mb-1">Welcome, {user?.full_name}</h2>
        <p className="text-muted-foreground mb-8">Choose the branch you are working at.</p>
        {active.length === 0 ? (
          <p className="text-muted-foreground">
            You are not assigned to any branch yet. Ask the academy owner to give you access.
          </p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {active.map((b) => (
              <button key={b.id} onClick={() => choose(b.id)} className="text-left">
                <Card className={`card-hover ${b.id === branchId ? "ring-2 ring-brand" : ""}`}>
                  <CardContent className="p-6 flex items-start gap-4">
                    <Building2 className="h-10 w-10 text-brand" />
                    <div>
                      <p className="text-lg font-semibold text-foreground">{b.name}</p>
                      <p className="text-sm text-muted-foreground flex items-center gap-1">
                        <MapPin className="h-3 w-3" /> {b.address ?? b.code}
                      </p>
                    </div>
                  </CardContent>
                </Card>
              </button>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
