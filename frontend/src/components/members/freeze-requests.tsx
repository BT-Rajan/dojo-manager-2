import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "wouter";
import { Snowflake } from "lucide-react";
import { Empty, Field, Loading, StatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useApiMutation } from "@/hooks/useApiMutation";
import { useAuth } from "@/hooks/useAuth";
import { useBranch } from "@/hooks/useBranch";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { api } from "@/lib/queryClient";
import type { MembershipRequest } from "@/lib/types";

/** Freeze requests (from the member portal) for the operations manager to decide. */
export function FreezeRequestsTab() {
  const { branchId } = useBranch();
  const { isManagement } = useAuth();
  const [show, setShow] = useState<"pending" | "all">("pending");
  const { data: rows = [], isLoading } = useQuery<MembershipRequest[]>({
    queryKey: ["/api/membership-requests", { branch_id: branchId, status: show === "pending" ? "pending" : undefined }],
    enabled: branchId !== null,
  });
  const [deciding, setDeciding] = useState<MembershipRequest | null>(null);
  const [note, setNote] = useState("");
  const decide = useApiMutation(
    (approve: boolean) => api(`/api/membership-requests/${deciding!.id}/decision`, { method: "POST", body: { approve, note: note || null } }),
    {
      invalidate: ["/api/membership-requests", "/api/members", "/api/memberships", "/api/dashboard"],
      success: "Decision saved",
      onSuccess: () => setDeciding(null),
    },
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant={show === "pending" ? "secondary" : "ghost"} onClick={() => setShow("pending")}>
          Waiting for a decision
        </Button>
        <Button size="sm" variant={show === "all" ? "secondary" : "ghost"} onClick={() => setShow("all")}>
          All
        </Button>
      </div>
      {isLoading ? (
        <Loading />
      ) : rows.length === 0 ? (
        <Empty icon={Snowflake}>{show === "pending" ? "No freeze requests waiting." : "No freeze requests."}</Empty>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Member</TableHead>
              <TableHead>Membership</TableHead>
              <TableHead>Freeze</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Requested</TableHead>
              <TableHead>Status</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.id}>
                <TableCell>
                  <Link href={`/members/${r.member_id}`} className="text-brand hover:underline">
                    {r.member_name}
                  </Link>
                </TableCell>
                <TableCell>
                  {r.plan_name}
                  <p className="text-xs text-muted-foreground">ends {fmtDate(r.membership_end)}</p>
                </TableCell>
                <TableCell>
                  {r.freeze_weeks} week{r.freeze_weeks === 1 ? "" : "s"} from {fmtDate(r.freeze_start)}
                </TableCell>
                <TableCell className="max-w-xs text-sm">{r.reason}</TableCell>
                <TableCell className="text-sm">
                  {fmtDateTime(r.created_at)}
                  {r.from_portal && <p className="text-xs text-muted-foreground">Member portal</p>}
                </TableCell>
                <TableCell>
                  <StatusBadge status={r.status} />
                  {r.decision_note && <p className="text-xs text-muted-foreground">{r.decision_note}</p>}
                </TableCell>
                <TableCell className="text-right">
                  {r.status === "pending" && isManagement && (
                    <Button
                      size="sm"
                      onClick={() => {
                        setNote("");
                        setDeciding(r);
                      }}
                    >
                      Review
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {!isManagement && <p className="text-xs text-muted-foreground">The operations manager approves or rejects freezes.</p>}
      <Dialog open={!!deciding} onOpenChange={(o) => !o && setDeciding(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Freeze for {deciding?.member_name}</DialogTitle>
          </DialogHeader>
          {deciding && (
            <p className="text-sm text-muted-foreground">
              {deciding.freeze_weeks} week(s) from {fmtDate(deciding.freeze_start)}. Approving pauses the membership and moves its end date
              from {fmtDate(deciding.membership_end)} by {deciding.freeze_weeks} week(s). One freeze per membership.
            </p>
          )}
          <Field label="Note (optional)">
            <Input value={note} maxLength={255} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <div className="flex gap-2">
            <Button disabled={decide.isPending} onClick={() => decide.mutate(true)}>
              Approve
            </Button>
            <Button variant="destructive" disabled={decide.isPending} onClick={() => decide.mutate(false)}>
              Reject
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
