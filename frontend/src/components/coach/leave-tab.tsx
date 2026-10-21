import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { addDays } from "date-fns";
import { CalendarOff, Plane, Send, Undo2, UserCheck } from "lucide-react";
import { Empty, EnumSelect, Field, Loading, RecordSelect, StatusBadge } from "@/components/common";
import { DateInput } from "@/components/common/date-inputs";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useApiMutation } from "@/hooks/useApiMutation";
import { useInstructors, usePrograms } from "@/hooks/useLookups";
import { fmtDate, fmtDateTime, fmtDay, fmtTime, isoDate, label } from "@/lib/format";
import { api } from "@/lib/queryClient";
import type { CoachSession, Leave } from "@/lib/types";
import { useCoach } from "./context";

const LEAVE_TYPES = ["annual", "sick", "emergency", "other"];

function days(l: Leave): number {
  const a = new Date(l.start_date);
  const b = new Date(l.end_date);
  return Math.round((b.getTime() - a.getTime()) / 86_400_000) + 1;
}

function RequestForm() {
  const { coach } = useCoach();
  const { instructors } = useInstructors(coach.branch_id);
  const today = coach.today;
  const [f, setF] = useState({ start_date: today, end_date: today, type: "annual", reason: "" });
  const [cover, setCover] = useState<number | null>(null);
  const send = useApiMutation(
    () =>
      api("/api/coach/leaves", {
        method: "POST",
        body: { ...f, reason: f.reason || null, cover_instructor_id: cover },
      }),
    {
      invalidate: ["/api/coach"],
      success: "Leave requested — a manager will approve it",
      onSuccess: () => {
        setF({ start_date: today, end_date: today, type: "annual", reason: "" });
        setCover(null);
      },
    },
  );
  const bad = !f.start_date || !f.end_date || f.end_date < f.start_date;
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base flex items-center gap-2">
          <Send className="h-4 w-4" aria-hidden="true" /> Request leave
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="From">
            <DateInput value={f.start_date} onChange={(d) => setF({ ...f, start_date: d })} />
          </Field>
          <Field label="To">
            <DateInput value={f.end_date} onChange={(d) => setF({ ...f, end_date: d })} />
          </Field>
          <Field label="Type">
            <EnumSelect value={f.type} onChange={(t) => setF({ ...f, type: t })} options={LEAVE_TYPES} />
          </Field>
          <Field label="Suggested cover (optional)">
            <RecordSelect
              value={cover}
              onChange={setCover}
              records={instructors.filter((i) => i.id !== coach.id && i.is_active)}
              render={(i) => i.full_name}
              allowNone="No suggestion"
            />
          </Field>
          <Field label="Reason (optional)" className="sm:col-span-2">
            <Input value={f.reason} maxLength={255} onChange={(e) => setF({ ...f, reason: e.target.value })} />
          </Field>
        </div>
        {f.end_date && f.start_date && f.end_date < f.start_date && (
          <p className="text-sm text-destructive">The end date is before the start date.</p>
        )}
        <Button disabled={bad || send.isPending} onClick={() => send.mutate(undefined)}>
          <Send className="h-4 w-4 mr-1" /> Send request
        </Button>
      </CardContent>
    </Card>
  );
}

function Covers() {
  const { coach, params } = useCoach();
  const { programMap } = usePrograms();
  const { instructorMap } = useInstructors(coach.branch_id);
  const [y, m, d] = coach.today.split("-").map(Number);
  const to = isoDate(addDays(new Date(y, m - 1, d), 30));
  const { data: sessions = [] } = useQuery<CoachSession[]>({
    queryKey: ["/api/coach/sessions", { ...params, date_from: coach.today, date_to: to }],
  });
  const covering = sessions.filter((s) => s.coach_role === "covering" && s.status !== "cancelled");
  const covered = sessions.filter((s) => s.coach_role === "covered" && s.status !== "cancelled");
  const row = (s: CoachSession, who: number | null) => (
    <li key={s.id} className="flex flex-wrap justify-between gap-2 rounded border p-2 text-sm">
      <span>
        {fmtDay(s.session_date)} · <span className="tabular">{fmtTime(s.start_time)}</span> ·{" "}
        {programMap.get(s.program_id)?.name}
      </span>
      <span className="text-muted-foreground">{who ? instructorMap.get(who)?.full_name : "No cover yet"}</span>
    </li>
  );
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <UserCheck className="h-4 w-4" aria-hidden="true" /> Classes you are covering
          </CardTitle>
        </CardHeader>
        <CardContent>
          {covering.length === 0 ? (
            <Empty>None in the next 30 days.</Empty>
          ) : (
            <ul className="space-y-2">{covering.map((s) => row(s, s.original_instructor_id))}</ul>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <Plane className="h-4 w-4" aria-hidden="true" /> Your classes being covered
          </CardTitle>
        </CardHeader>
        <CardContent>
          {covered.length === 0 ? (
            <Empty>None in the next 30 days.</Empty>
          ) : (
            <ul className="space-y-2">{covered.map((s) => row(s, s.instructor_id))}</ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

/** Leave: request it, follow the manager's decision, and see who covers whom. */
export function LeaveTab() {
  const { coach, params, isSelf } = useCoach();
  const { instructorMap } = useInstructors(coach.branch_id);
  const { data: leaves = [], isLoading } = useQuery<Leave[]>({ queryKey: ["/api/coach/leaves", params] });
  const withdraw = useApiMutation(
    (id: number) => api(`/api/coach/leaves/${id}/withdraw`, { method: "POST" }),
    { invalidate: ["/api/coach"], success: "Request withdrawn" },
  );
  const year = coach.today.slice(0, 4);
  const taken = leaves
    .filter((l) => l.status === "approved" && l.start_date.startsWith(year))
    .reduce((t, l) => t + days(l), 0);
  const pending = leaves.filter((l) => l.status === "pending").length;

  return (
    <div className="space-y-4">
      {isSelf && <RequestForm />}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex flex-wrap items-center justify-between gap-2">
            <span className="flex items-center gap-2">
              <CalendarOff className="h-4 w-4" aria-hidden="true" /> {isSelf ? "Your leave" : "Leave"}
            </span>
            <span className="text-sm font-normal text-muted-foreground">
              {taken} day{taken === 1 ? "" : "s"} approved in {year} · {pending} pending
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Loading rows={3} />
          ) : leaves.length === 0 ? (
            <Empty>No leave requested yet.</Empty>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>From</TableHead>
                  <TableHead>To</TableHead>
                  <TableHead className="text-right">Days</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Cover</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Manager's note</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {leaves.map((l) => (
                  <TableRow key={l.id}>
                    <TableCell>{fmtDate(l.start_date)}</TableCell>
                    <TableCell>{fmtDate(l.end_date)}</TableCell>
                    <TableCell className="text-right tabular">{days(l)}</TableCell>
                    <TableCell>
                      {label(l.type)}
                      {l.reason && <p className="text-xs text-muted-foreground">{l.reason}</p>}
                    </TableCell>
                    <TableCell>{l.cover_instructor_id ? instructorMap.get(l.cover_instructor_id)?.full_name : "—"}</TableCell>
                    <TableCell>
                      <StatusBadge status={l.status} />
                      {l.decided_at && l.status !== "cancelled" && (
                        <p className="text-xs text-muted-foreground">{fmtDateTime(l.decided_at)}</p>
                      )}
                    </TableCell>
                    <TableCell className="text-sm">{l.decision_note ?? "—"}</TableCell>
                    <TableCell className="text-right">
                      {isSelf && l.status === "pending" && (
                        <Button size="sm" variant="ghost" onClick={() => withdraw.mutate(l.id)} disabled={withdraw.isPending}>
                          <Undo2 className="h-4 w-4 mr-1" /> Withdraw
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <Covers />
    </div>
  );
}
