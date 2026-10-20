import { Link } from "wouter";
import { Compass } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardContent className="pt-8 pb-6 text-center space-y-4">
          <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-muted">
            <Compass className="h-6 w-6 text-muted-foreground" aria-hidden="true" />
          </span>
          <div className="space-y-1">
            <h1 className="text-2xl font-semibold tracking-tight text-foreground">Page not found</h1>
            <p className="text-sm text-muted-foreground">The page you are looking for doesn't exist or has moved.</p>
          </div>
          <Button asChild>
            <Link href="/">Back to start</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
