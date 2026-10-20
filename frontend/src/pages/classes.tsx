import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { addDays, startOfWeek } from "date-fns";
import { CalendarPlus, ChevronLeft, ChevronRight, Plus, Users, XCircle } from "lucide-react";
import { Page } from "@/components/layout/page";
import { Empty, EnumSelect, Field, RecordSelect, StatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApiMutation } from "@/hooks/useApiMutation";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/hooks/useAuth";
import { useBranch } from "@/hooks/useBranch";
import { useInstructors, usePrograms } from "@/hooks/useLookups";
import { WEEKDAYS, academyToday, dmy, fmtDate, fmtDay, fmtTime, isoDate, label } from "@/lib/format";
import { api } from "@/lib/queryClient";
import type { AttendanceRow, AttendanceStatus, ClassSession, Leave, Member, Schedule } from "@/lib/types";
import { DateInput, TimeInput } from "@/components/common/date-inputs";

const ATT_STATUSES: AttendanceStatus[] = ["booked", "present", "late", "absent", "excused"];

function AttendanceDialog({ session, onClose }: { session: ClassSession; onClose: () => void }) {
  const { isStaff } = useAuth();
  const [q, setQ] = useState("");
  const [reason, setReason] = useState("");
  const url = `/api/sessions/${session.id}/attendance`;
  const { data: rows = [] } = useQuery<AttendanceRow[]>({ queryKey: [url] });
  const { data: found = [] } = useQuery<Member[]>({
    queryKey: ["/api/members", { branch_id: session.branch_id, q: q.trim(), status: "active", limit: 10 }],
    enabled: q.trim().length >= 2,
  });
  const record = useApiMutation(
    (entries: { member_id: number; status: AttendanceStatus }[]) =>
      api(url, { method: "POST", body: { entries } }),
    { invalidate: [url, "/api/sessions", "/api/dashboard"] },
  );
  const cancel = useApiMutation(
    () =>
      api(`/api/sessions/${session.id}`, {
        method: "PATCH",
        body: { status: "cancelled", change_reason: reason, members_notified: true },
      }),
    { invalidate: ["/api/sessions", "/api/dashboard"], success: "Class cancelled", onSuccess: onClose },
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
        <p className="text-sm text-red-700">Cancelled: {session.change_reason}</p>
      ) : (
        <>
          <p className="text-sm text-gray-500">
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
                  {m.full_name} <span className="text-gray-400">{m.phone}</span>
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
      {rows.length === 0 ? (
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
                    <span className="text-xs text-red-700">Not covered on this date</span>
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

function SessionsTab() {
  const { branchId } = useBranch();
  const { isStaff } = useAuth();
  const { programMap } = usePrograms();
  const { instructorMap } = useInstructors(branchId);
  // Academy weeks run Saturday to Friday.
  const [weekStart, setWeekStart] = useState(() => startOfWeek(academyToday(), { weekStartsOn: 6 }));
  const [selected, setSelected] = useState<ClassSession | null>(null);
  const from = isoDate(weekStart);
  const to = isoDate(addDays(weekStart, 6));
  const { data: sessions = [] } = useQuery<ClassSession[]>({
    queryKey: ["/api/sessions", { branch_id: branchId, date_from: from, date_to: to }],
    enabled: branchId !== null,
  });
  const generate = useApiMutation(
    () => api<{ created: number }>("/api/sessions/generate", { method: "POST", body: { branch_id: branchId, date_from: from, date_to: to } }),
    { invalidate: ["/api/sessions", "/api/dashboard"], success: "Week generated from timetable" },
  );
  const byDay = useMemo(() => {
    const m = new Map<string, ClassSession[]>();
    for (const s of sessions) m.set(s.session_date, [...(m.get(s.session_date) ?? []), s]);
    return [...m.entries()];
  }, [sessions]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="icon" onClick={() => setWeekStart(addDays(weekStart, -7))} aria-label="Previous week">
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="font-medium">
          {dmy(weekStart)} – {dmy(addDays(weekStart, 6))}
        </span>
        <Button variant="outline" size="icon" onClick={() => setWeekStart(addDays(weekStart, 7))} aria-label="Next week">
          <ChevronRight className="h-4 w-4" />
        </Button>
        {isStaff && (
          <Button variant="outline" onClick={() => generate.mutate(undefined)} disabled={generate.isPending}>
            <CalendarPlus className="h-4 w-4 mr-1" /> Generate week from timetable
          </Button>
        )}
      </div>
      {byDay.length === 0 ? (
        <Empty>No classes this week.</Empty>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {byDay.map(([day, list]) => (
            <Card key={day}>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">{fmtDay(day)}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {list.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => setSelected(s)}
                    className={`w-full text-left rounded border p-2 hover:bg-gray-50 ${s.status === "cancelled" ? "opacity-60" : ""}`}
                  >
                    <div className="flex justify-between text-sm font-medium">
                      <span>
                        {fmtTime(s.start_time)} {programMap.get(s.program_id)?.name}
                      </span>
                      {s.status !== "scheduled" && <StatusBadge status={s.status} />}
                    </div>
                    <div className="flex justify-between text-xs text-gray-500">
                      <span>
                        {s.instructor_id ? instructorMap.get(s.instructor_id)?.full_name : "No instructor"}
                        {s.original_instructor_id && (
                          <span className="text-amber-700">
                            {" "}
                            (covering {instructorMap.get(s.original_instructor_id)?.full_name ?? "instructor on leave"})
                          </span>
                        )}
                      </span>
                      <span className="flex items-center gap-1">
                        <Users className="h-3 w-3" /> {s.booked}/{s.capacity} · {s.attended} present
                      </span>
                    </div>
                  </button>
                ))}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      <Dialog open={!!selected} onOpenChange={(o) => !o && setSelected(null)}>
        {selected && <AttendanceDialog session={selected} onClose={() => setSelected(null)} />}
      </Dialog>
    </div>
  );
}

function TimetableTab() {
  const { branchId } = useBranch();
  const { isStaff } = useAuth();
  const { programs, programMap } = usePrograms();
  const { instructors, instructorMap } = useInstructors(branchId);
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ weekday: "6", start_time: "16:30:00", end_time: "17:10:00", capacity: "20" });
  const [programId, setProgramId] = useState<number | null>(null);
  const [instructorId, setInstructorId] = useState<number | null>(null);
  const { data: schedules = [] } = useQuery<Schedule[]>({
    queryKey: ["/api/schedules", { branch_id: branchId }],
    enabled: branchId !== null,
  });
  const create = useApiMutation(
    () =>
      api("/api/schedules", {
        method: "POST",
        body: {
          branch_id: branchId,
          program_id: programId,
          instructor_id: instructorId,
          weekday: Number(f.weekday),
          start_time: f.start_time,
          end_time: f.end_time,
          capacity: Number(f.capacity),
        },
      }),
    { invalidate: ["/api/schedules"], success: "Class added to timetable", onSuccess: () => setOpen(false) },
  );
  const deactivate = useApiMutation(
    (id: number) => api(`/api/schedules/${id}`, { method: "PATCH", body: { is_active: false } }),
    { invalidate: ["/api/schedules"], success: "Removed from timetable" },
  );
  const order = [6, 7, 1, 2, 3, 4, 5];

  return (
    <div className="space-y-4">
      {isStaff && (
        <Button onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4 mr-1" /> Add weekly class
        </Button>
      )}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {order
          .filter((d) => schedules.some((s) => s.weekday === d))
          .map((d) => (
            <Card key={d}>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">{WEEKDAYS[d]}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm">
                {schedules
                  .filter((s) => s.weekday === d)
                  .map((s) => (
                    <div key={s.id} className="flex justify-between items-center">
                      <span>
                        {fmtTime(s.start_time)}–{fmtTime(s.end_time)} {programMap.get(s.program_id)?.name}
                        <span className="text-gray-400"> {s.instructor_id ? instructorMap.get(s.instructor_id)?.full_name : ""}</span>
                      </span>
                      {isStaff && (
                        <Button variant="ghost" size="sm" onClick={() => deactivate.mutate(s.id)} aria-label="Remove">
                          <XCircle className="h-4 w-4 text-gray-400" />
                        </Button>
                      )}
                    </div>
                  ))}
              </CardContent>
            </Card>
          ))}
      </div>
      {schedules.length === 0 && <Empty>No weekly classes set up.</Empty>}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add weekly class</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Programme" className="sm:col-span-2">
              <RecordSelect value={programId} onChange={setProgramId} records={programs} render={(p) => p.name} />
            </Field>
            <Field label="Instructor" className="sm:col-span-2">
              <RecordSelect value={instructorId} onChange={setInstructorId} records={instructors} render={(i) => i.full_name} allowNone="Unassigned" />
            </Field>
            <Field label="Day">
              <EnumSelect
                value={f.weekday}
                onChange={(v) => setF({ ...f, weekday: v })}
                options={["6", "7", "1", "2", "3", "4", "5"]}
                labels={Object.fromEntries([1, 2, 3, 4, 5, 6, 7].map((d) => [String(d), WEEKDAYS[d]]))}
              />
            </Field>
            <Field label="Capacity">
              <Input type="number" min={1} value={f.capacity} onChange={(e) => setF({ ...f, capacity: e.target.value })} />
            </Field>
            <Field label="Starts">
              <TimeInput value={f.start_time} onChange={(t) => setF({ ...f, start_time: t })} />
            </Field>
            <Field label="Ends">
              <TimeInput value={f.end_time} onChange={(t) => setF({ ...f, end_time: t })} />
            </Field>
          </div>
          <Button disabled={!programId || !f.start_time || !f.end_time || create.isPending} onClick={() => create.mutate(undefined)}>
            Save
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function LeaveTab() {
  const { branchId } = useBranch();
  const { isStaff } = useAuth();
  const { instructors, instructorMap } = useInstructors(branchId);
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ start_date: isoDate(), end_date: isoDate(), type: "annual", reason: "" });
  const [who, setWho] = useState<number | null>(null);
  const [cover, setCover] = useState<number | null>(null);
  const { data: leaves = [] } = useQuery<Leave[]>({
    queryKey: ["/api/leaves", { branch_id: branchId }],
    enabled: branchId !== null,
  });
  const { toast } = useToast();
  // Leave changes who teaches already-generated classes, so refresh those too.
  const affected = ["/api/leaves", "/api/sessions", "/api/dashboard"];
  const create = useApiMutation(
    () =>
      api<{ sessions_reassigned: number }>("/api/leaves", {
        method: "POST",
        body: { ...f, reason: f.reason || null, instructor_id: who, cover_instructor_id: cover },
      }),
    {
      invalidate: affected,
      onSuccess: (r) => {
        setOpen(false);
        const n = r.sessions_reassigned;
        toast({
          title: "Leave recorded",
          description: n ? `${n} scheduled class(es) handed to ${cover ? "the cover instructor" : "no one — assign a cover"}` : undefined,
        });
      },
    },
  );
  const remove = useApiMutation((id: number) => api(`/api/leaves/${id}`, { method: "DELETE" }), {
    invalidate: affected,
    success: "Leave removed; covered classes returned to the instructor",
  });

  return (
    <div className="space-y-4">
      {isStaff && (
        <Button onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4 mr-1" /> Record leave
        </Button>
      )}
      {leaves.length === 0 ? (
        <Empty>No instructor leave recorded.</Empty>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Instructor</TableHead>
              <TableHead>From</TableHead>
              <TableHead>To</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Cover</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {leaves.map((l) => (
              <TableRow key={l.id}>
                <TableCell>{instructorMap.get(l.instructor_id)?.full_name}</TableCell>
                <TableCell>{fmtDate(l.start_date)}</TableCell>
                <TableCell>{fmtDate(l.end_date)}</TableCell>
                <TableCell>{label(l.type)}</TableCell>
                <TableCell>{l.cover_instructor_id ? instructorMap.get(l.cover_instructor_id)?.full_name : "—"}</TableCell>
                <TableCell>
                  {isStaff && (
                    <Button variant="ghost" size="sm" onClick={() => remove.mutate(l.id)}>
                      Remove
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Record instructor leave</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Instructor" className="sm:col-span-2">
              <RecordSelect value={who} onChange={setWho} records={instructors} render={(i) => i.full_name} />
            </Field>
            <Field label="From">
              <DateInput value={f.start_date} onChange={(d) => setF({ ...f, start_date: d })} />
            </Field>
            <Field label="To">
              <DateInput value={f.end_date} onChange={(d) => setF({ ...f, end_date: d })} />
            </Field>
            <Field label="Type">
              <EnumSelect value={f.type} onChange={(t) => setF({ ...f, type: t })} options={["annual", "sick", "emergency", "other"]} />
            </Field>
            <Field label="Cover instructor">
              <RecordSelect
                value={cover}
                onChange={setCover}
                records={instructors.filter((i) => i.id !== who)}
                render={(i) => i.full_name}
                allowNone="No cover"
              />
            </Field>
            <Field label="Reason" className="sm:col-span-2">
              <Input value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} />
            </Field>
          </div>
          <Button disabled={!who || !f.start_date || !f.end_date || create.isPending} onClick={() => create.mutate(undefined)}>
            Save
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function Classes() {
  return (
    <Page title="Classes">
      <Tabs defaultValue="sessions">
        <TabsList>
          <TabsTrigger value="sessions">This week</TabsTrigger>
          <TabsTrigger value="timetable">Weekly timetable</TabsTrigger>
          <TabsTrigger value="leave">Instructor leave</TabsTrigger>
        </TabsList>
        <TabsContent value="sessions">
          <SessionsTab />
        </TabsContent>
        <TabsContent value="timetable">
          <TimetableTab />
        </TabsContent>
        <TabsContent value="leave">
          <LeaveTab />
        </TabsContent>
      </Tabs>
    </Page>
  );
}
