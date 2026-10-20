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
import { cn } from "@/lib/utils";

type NavItem = { path: string; label: string; icon: typeof Home; show: boolean };

function initials(name: string | undefined) {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase() || "?";
}

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
    <header className="sticky top-0 z-50 border-b border-border bg-card/85 backdrop-blur supports-[backdrop-filter]:bg-card/75">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex flex-wrap items-center justify-between gap-2 py-3">
          <Link href="/" className="group flex items-center gap-3 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg brand-gradient shadow-sm transition-transform group-hover:scale-105">
              <Swords className="h-5 w-5 text-white" aria-hidden="true" />
            </span>
            <span className="text-lg font-semibold tracking-tight text-foreground">Dojo Manager</span>
          </Link>

          <div className="flex items-center gap-3">
            {branches.length > 0 && (
              <Select
                value={branchId ? String(branchId) : undefined}
                onValueChange={(v) => setSelectedBranch(Number(v))}
              >
                <SelectTrigger className="h-9 w-44" aria-label="Branch">
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
              <div className="flex items-center gap-2.5">
                <span
                  className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold text-primary"
                  aria-hidden="true"
                >
                  {initials(user.full_name)}
                </span>
                <div className="hidden leading-tight md:block">
                  <p className="text-sm font-medium text-foreground">{user.full_name}</p>
                  <p className="text-xs text-muted-foreground">{ROLE_LABELS[user.role]}</p>
                </div>
              </div>
            )}
            <Button
              variant="ghost"
              size="icon"
              onClick={logout}
              className="h-9 w-9 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
              aria-label="Sign out"
              title="Sign out"
            >
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <nav aria-label="Main" className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-2.5 [scrollbar-width:none] sm:flex-wrap sm:overflow-visible [&::-webkit-scrollbar]:hidden">
          {nav
            .filter((n) => n.show)
            .map(({ path, label, icon: Icon }) => {
              const active = location === path || location.startsWith(`${path}/`);
              return (
                <Link
                  key={path}
                  href={path}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "inline-flex h-9 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-md px-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    active
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  <Icon className="h-4 w-4" aria-hidden="true" />
                  {label}
                </Link>
              );
            })}
        </nav>
      </div>
    </header>
  );
}
