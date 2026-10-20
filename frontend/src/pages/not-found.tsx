import { Link } from "wouter";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
      <Card className="w-full max-w-md">
        <CardContent className="pt-6 text-center space-y-4">
          <h1 className="text-2xl font-bold text-gray-900">Page not found</h1>
          <Button asChild>
            <Link href="/">Back to start</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
