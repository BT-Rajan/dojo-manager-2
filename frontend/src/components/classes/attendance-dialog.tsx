import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { XCircle } from "lucide-react";
import { Empty, EnumSelect, Loading, StatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useApiMutation } from "@/hooks/useApiMutation";
import { useAuth } from "@/hooks/useAuth";
import { fmtDate, fmtTime } from "@/lib/format";
import { api } from "@/lib/queryClient";
import type { AttendanceRow, AttendanceStatus, ClassSession, Member } from "@/lib/types";

const ATT_STATUSES: AttendanceStatus[] = ["booked", "present", "late", "absent", "excused"];

/** Book members into a class and mark who came; staff can also cancel the class. */
export function AttendanceDialog({ session, onClose }: { session: ClassSession; onClose: () => void }) {
  const { isStaff } = useAuth();
  const [q, setQ] = useState("");
  const [reason, setReason] = useState("");
  const url = `/api/sessions/${session.id}/attendance`;
  const { data: rows = [], isLoading: loading_rows } = useQuery<AttendanceRow[]>({ queryKey: [url] });
  const { data: found = [] } = useQuery<Member[]>({
    queryKey: ["/api/members", { branch_id: session.branch_id, q: q.trim(), status: "active", limit: 10 }],
    enabled: q.trim().length >= 2,
  });
  const record = useApiMutation(
    (entries: { member_id: number; status: AttendanceStatus }[]) =>
      api(url, { method: "POST", body: { entries } }),
    { invalidate: [url, "/api/sessions", "/api/dashboard", "/api/coach"] },
  );
  const cancel = useApiMutation(
    () =>
      api(`/api/sessions/${session.id}`, {
        method: "PATCH",
        body: { status: "cancelled", change_reason: reason, members_notified: true },
      }),
    { invalidate: ["/api/sessions", "/api/dashboard", "/api/coach"], success: "Class cancelled", onSuccess: onClose },
  );
  const already = new Set(rows.map((r) => r.member_id));
  const cancelled = session.status === "cancelled";

  return (
    <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
      <DialogHeader>
        <DialogTitle>
          {fmtDate(session.session_date)} · {fmtTime(session.start_time)}–{fmtTime(session.end_time)}
        </DialogTitle>
      </DialogHeader>
      {cancelled ? (
        <p className="text-sm text-destructive">Cancelled: {session.change_reason}</p>
      ) : (
        <>
          <p className="text-sm text-muted-foreground">
            {rows.filter((r) => ["booked", "present", "late"].includes(r.status)).length} / {session.capacity} places taken
          </p>
          <div className="flex gap-2">
            <Input placeholder="Find member to add (name or phone)" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          {found
            .filter((m) => !already.has(m.id))
            .map((m) => (
              <div key={m.id} className="flex items-center justify-between text-sm border rounded p-2">
                <span>
                  {m.full_name} <span className="text-muted-foreground/70">{m.phone}</span>
                </span>
                <span className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => record.mutate([{ member_id: m.id, status: "booked" }])}>
                    Book
                  </Button>
                  <Button size="sm" onClick={() => record.mutate([{ member_id: m.id, status: "present" }])}>
                    Check in
                  </Button>
                </span>
              </div>
            ))}
        </>
      )}
      {loading_rows ? <Loading /> : rows.length === 0 ? (
        <Empty>No one booked yet.</Empty>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Member</TableHead>
              <TableHead>Membership</TableHead>
              <TableHead className="w-40">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.id}>
                <TableCell>
                  {r.member.first_name} {r.member.last_name}
                </TableCell>
                <TableCell>
                  {r.has_active_membership ? (
                    <StatusBadge status="active" />
                  ) : (
                    <span className="text-xs text-destructive">Not covered on this date</span>
                  )}
                </TableCell>
                <TableCell>
                  {cancelled ? (
                    <StatusBadge status={r.status} />
                  ) : (
                    <EnumSelect
                      value={r.status}
                      onChange={(s) => record.mutate([{ member_id: r.member_id, status: s as AttendanceStatus }])}
                      options={ATT_STATUSES}
                    />
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {isStaff && !cancelled && (
        <div className="border-t pt-4 flex gap-2">
          <Input placeholder="Reason for cancelling" value={reason} onChange={(e) => setReason(e.target.value)} />
          <Button variant="destructive" disabled={reason.trim().length < 3 || cancel.isPending} onClick={() => cancel.mutate(undefined)}>
            <XCircle className="h-4 w-4 mr-1" /> Cancel class
          </Button>
        </div>
      )}
    </DialogContent>
  );
}
