import type { ReactNode } from "react";
import { Link } from "wouter";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useBranch } from "@/hooks/useBranch";

/** Standard page frame. With `needsBranch`, children render only once a branch is chosen. */
export function Page({
  title,
  subtitle,
  actions,
  needsBranch = true,
  children,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  needsBranch?: boolean;
  children: ReactNode;
}) {
  const { branch } = useBranch();
  return (
    <div className="min-h-screen bg-background">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-sm focus:text-primary-foreground"
      >
        Skip to content
      </a>
      <Header />
      <main id="main" className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">{title}</h2>
            {(subtitle ?? (needsBranch && branch ? `${branch.name} branch` : "")) && (
              <p className="mt-1 text-sm text-muted-foreground">
                {subtitle ?? `${branch?.name} branch`}
              </p>
            )}
          </div>
          {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
        </div>
        {needsBranch && !branch ? (
          <Card>
            <CardContent className="py-10 text-center space-y-3">
              <p className="text-muted-foreground">Choose a branch to continue.</p>
              <Button asChild>
                <Link href="/">Choose branch</Link>
              </Button>
            </CardContent>
          </Card>
        ) : (
          children
        )}
      </main>
    </div>
  );
}
