import { Link, useLocation } from "wouter";
import {
  Award,
  BarChart3,
  CalendarDays,
  ClipboardList,
  Home,
  LogOut,
  Package,
  Shield,
  Swords,
  UserPlus,
  Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuth } from "@/hooks/useAuth";
import { setSelectedBranch, useBranch } from "@/hooks/useBranch";
import { api, queryClient } from "@/lib/queryClient";
import { ROLE_LABELS } from "@/lib/format";

type NavItem = { path: string; label: string; icon: typeof Home; show: boolean };

export function Header() {
  const { user, isManagement, isStaff } = useAuth();
  const { branchId, branches } = useBranch();
  const [location, setLocation] = useLocation();

  const nav: NavItem[] = [
    { path: "/dashboard", label: "Dashboard", icon: Home, show: true },
    { path: "/members", label: "Members", icon: Users, show: true },
    { path: "/classes", label: "Classes", icon: CalendarDays, show: true },
    { path: "/leads", label: "Leads", icon: UserPlus, show: isStaff },
    { path: "/gradings", label: "Gradings", icon: Award, show: true },
    { path: "/inventory", label: "Inventory", icon: Package, show: isStaff },
    { path: "/operations", label: "Operations", icon: ClipboardList, show: true },
    { path: "/reports", label: "Reports", icon: BarChart3, show: isStaff },
    { path: "/admin", label: "Admin", icon: Shield, show: isManagement },
  ];

  const logout = async () => {
    await api("/api/auth/logout", { method: "POST" }).catch(() => undefined);
    queryClient.clear();
    setLocation("/");
    window.location.reload();
  };

  return (
    <header className="bg-card shadow-sm border-b border-border sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-wrap justify-between items-center gap-2 py-3">
          <Link href="/" className="flex items-center">
            <Swords className="h-6 w-6 text-brand mr-3" />
            <h1 className="text-xl font-semibold text-foreground">Dojo Manager</h1>
          </Link>

          <div className="flex items-center gap-3">
            {branches.length > 0 && (
              <Select
                value={branchId ? String(branchId) : undefined}
                onValueChange={(v) => setSelectedBranch(Number(v))}
              >
                <SelectTrigger className="w-44" aria-label="Branch">
                  <SelectValue placeholder="Select branch" />
                </SelectTrigger>
                <SelectContent>
                  {branches.map((b) => (
                    <SelectItem key={b.id} value={String(b.id)}>
                      {b.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            {user && (
              <div className="text-sm text-muted-foreground hidden md:block">
                <span>{user.full_name}</span>
                <span className="text-muted-foreground/70 ml-2">{ROLE_LABELS[user.role]}</span>
              </div>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={logout}
              className="text-destructive hover:text-destructive hover:bg-destructive/10"
              aria-label="Sign out"
            >
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <nav className="flex flex-wrap gap-1 pb-3">
          {nav
            .filter((n) => n.show)
            .map(({ path, label, icon: Icon }) => {
              const active = location === path || location.startsWith(`${path}/`);
              return (
                <Button
                  key={path}
                  asChild
                  variant={active ? "default" : "ghost"}
                  size="sm"
                  className=""
                >
                  <Link href={path}>
                    <Icon className="h-4 w-4 mr-1" />
                    {label}
                  </Link>
                </Button>
              );
            })}
        </nav>
      </div>
    </header>
  );
}
