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
    <div className="min-h-screen bg-gray-50">
      <Header />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-2xl font-bold text-gray-900">{title}</h2>
            <p className="text-sm text-gray-500">
              {subtitle ?? (needsBranch && branch ? `${branch.name} branch` : "")}
            </p>
          </div>
          {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
        </div>
        {needsBranch && !branch ? (
          <Card>
            <CardContent className="py-10 text-center space-y-3">
              <p className="text-gray-600">Choose a branch to continue.</p>
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
