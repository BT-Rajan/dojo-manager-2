import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useLocation } from "wouter";
import { Plus, Search } from "lucide-react";
import { Page } from "@/components/layout/page";
import { BeltSwatch, Empty, EnumSelect, StatusBadge } from "@/components/common";
import { MemberForm, toPayload } from "@/components/common/member-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useApiMutation } from "@/hooks/useApiMutation";
import { useAuth } from "@/hooks/useAuth";
import { useBranch } from "@/hooks/useBranch";
import { api } from "@/lib/queryClient";
import type { Member } from "@/lib/types";

export default function Members() {
  const { branchId } = useBranch();
  const { isStaff } = useAuth();
  const [, setLocation] = useLocation();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<string>("active");
  const [open, setOpen] = useState(false);

  const { data: members = [], isLoading } = useQuery<Member[]>({
    queryKey: ["/api/members", { branch_id: branchId, q: q.trim() || undefined, status: status === "all" ? undefined : status }],
    enabled: branchId !== null,
  });

  const create = useApiMutation(
    (body: Record<string, unknown>) => api<Member>("/api/members", { method: "POST", body }),
    {
      invalidate: ["/api/members", "/api/dashboard"],
      success: "Member registered",
      onSuccess: (m) => {
        setOpen(false);
        setLocation(`/members/${m.id}`);
      },
    },
  );

  return (
    <Page
      title="Members"
      actions={
        isStaff && (
          <Button onClick={() => setOpen(true)}>
            <Plus className="h-4 w-4 mr-1" /> Register member
          </Button>
        )
      }
    >
      <Card>
        <CardContent className="p-4 space-y-4">
          <div className="flex flex-wrap gap-3">
            <div className="relative flex-1 min-w-[220px]">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
              <Input
                className="pl-9"
                placeholder="Search name, phone, member no. or civil ID"
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
            </div>
            <div className="w-40">
              <EnumSelect value={status} onChange={setStatus} options={["active", "frozen", "inactive", "all"]} />
            </div>
          </div>
          {isLoading ? (
            <Empty>Loading…</Empty>
          ) : members.length === 0 ? (
            <Empty>No members found.</Empty>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>No.</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Age</TableHead>
                  <TableHead>Phone</TableHead>
                  <TableHead>Belt</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {members.map((m) => (
                  <TableRow key={m.id}>
                    <TableCell className="font-mono text-xs">{m.member_no}</TableCell>
                    <TableCell>
                      <Link href={`/members/${m.id}`} className="text-brand hover:underline">
                        {m.full_name}
                      </Link>
                    </TableCell>
                    <TableCell>{m.age ?? "—"}</TableCell>
                    <TableCell>{m.phone}</TableCell>
                    <TableCell>
                      {m.belt_rank ? (
                        <BeltSwatch color={m.belt_rank.color} name={`${m.belt_rank.name}${m.stripes ? ` +${m.stripes}` : ""}`} />
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={m.status} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Register member</DialogTitle>
          </DialogHeader>
          <MemberForm
            submitLabel="Register"
            busy={create.isPending}
            onSubmit={(v) => create.mutate({ ...toPayload(v), branch_id: branchId })}
          />
        </DialogContent>
      </Dialog>
    </Page>
  );
}
