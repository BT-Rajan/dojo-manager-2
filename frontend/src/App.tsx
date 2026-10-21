import { lazy, Suspense } from "react";
import { Route, Switch, useLocation } from "wouter";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useAuth } from "@/hooks/useAuth";
import { queryClient } from "@/lib/queryClient";
import Admin from "@/pages/admin";
import Classes from "@/pages/classes";
import Coach from "@/pages/coach";
import Dashboard from "@/pages/dashboard";
import Gradings from "@/pages/gradings";
import Home from "@/pages/home";
import Inventory from "@/pages/inventory";
import Leads from "@/pages/leads";
import Login from "@/pages/login";
import MemberDetail from "@/pages/member-detail";
import Members from "@/pages/members";
import NotFound from "@/pages/not-found";
import Operations from "@/pages/operations";
import Reports from "@/pages/reports";

// The member and parent portal is a separate app for families, loaded only on /portal.
const PortalApp = lazy(() => import("@/portal/portal-app"));

const LoadingScreen = () => (
  <div className="flex items-center justify-center min-h-screen bg-background">
    <div className="text-center">
      <div className="animate-spin rounded-full h-10 w-10 border-2 border-muted border-t-primary mx-auto mb-4" />
      <p className="text-muted-foreground">Loading...</p>
    </div>
  </div>
);

function Router() {
  const [location] = useLocation();
  if (location === "/portal" || location.startsWith("/portal/")) {
    return (
      <Suspense fallback={null}>
        <PortalApp />
      </Suspense>
    );
  }
  return <StaffRouter />;
}

function StaffRouter() {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) return <LoadingScreen />;
  if (!isAuthenticated) return <Login />;
  return (
    <Switch>
      <Route path="/" component={Home} />
      <Route path="/dashboard" component={Dashboard} />
      <Route path="/members" component={Members} />
      <Route path="/members/:id" component={MemberDetail} />
      <Route path="/classes" component={Classes} />
      <Route path="/coach" component={Coach} />
      <Route path="/leads" component={Leads} />
      <Route path="/gradings" component={Gradings} />
      <Route path="/inventory" component={Inventory} />
      <Route path="/operations" component={Operations} />
      <Route path="/reports" component={Reports} />
      <Route path="/admin" component={Admin} />
      <Route component={NotFound} />
    </Switch>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <Toaster />
        <Router />
      </TooltipProvider>
    </QueryClientProvider>
  );
}
