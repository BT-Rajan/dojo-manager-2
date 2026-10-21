import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { addDays, startOfWeek } from "date-fns";
import { CalendarPlus, ChevronLeft, ChevronRight, Plus, Users, XCircle } from "lucide-react";
import { AttendanceDialog } from "@/components/classes/attendance-dialog";
import { Page } from "@/components/layout/page";
import { Empty, EnumSelect, Field, Loading, RecordSelect, StatusBadge } from "@/components/common";
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
import type { ClassSession, Leave, Schedule } from "@/lib/types";
import { DateInput, TimeInput } from "@/components/common/date-inputs";

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
  const { data: sessions = [], isLoading: loading_sessions } = useQuery<ClassSession[]>({
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
      {loading_sessions ? <Loading /> : byDay.length === 0 ? (
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
                    className={`w-full text-left rounded border p-2 hover:bg-muted/50 ${s.status === "cancelled" ? "opacity-60" : ""}`}
                  >
                    <div className="flex justify-between text-sm font-medium">
                      <span>
                        {fmtTime(s.start_time)} {programMap.get(s.program_id)?.name}
                      </span>
                      {s.status !== "scheduled" && <StatusBadge status={s.status} />}
                    </div>
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>
                        {s.instructor_id ? instructorMap.get(s.instructor_id)?.full_name : "No instructor"}
                        {s.original_instructor_id && (
                          <span className="text-warning">
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
  const { data: schedules = [], isLoading: loading_schedules } = useQuery<Schedule[]>({
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
                        <span className="text-muted-foreground/70"> {s.instructor_id ? instructorMap.get(s.instructor_id)?.full_name : ""}</span>
                      </span>
                      {isStaff && (
                        <Button variant="ghost" size="sm" onClick={() => deactivate.mutate(s.id)} aria-label="Remove">
                          <XCircle className="h-4 w-4 text-muted-foreground/70" />
                        </Button>
                      )}
                    </div>
                  ))}
              </CardContent>
            </Card>
          ))}
      </div>
      {loading_schedules ? <Loading /> : schedules.length === 0 && <Empty>No weekly classes set up.</Empty>}
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
  const { data: leaves = [], isLoading: loading_leaves } = useQuery<Leave[]>({
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
  const [deciding, setDeciding] = useState<Leave | null>(null);
  const [decision, setDecision] = useState({ note: "", cover: null as number | null });
  const decide = useApiMutation(
    (approve: boolean) =>
      api<{ sessions_reassigned: number; status: string }>(`/api/leaves/${deciding!.id}/decision`, {
        method: "POST",
        body: approve
          ? { approve, note: decision.note || null, cover_instructor_id: decision.cover }
          : { approve, note: decision.note || null },
      }),
    {
      invalidate: [...affected, "/api/coach"],
      onSuccess: (r) => {
        setDeciding(null);
        toast({
          title: r.status === "approved" ? "Leave approved" : "Leave rejected",
          description: r.sessions_reassigned ? `${r.sessions_reassigned} class(es) handed to the cover` : undefined,
        });
      },
    },
  );
  const [show, setShow] = useState<"all" | "pending">("all");
  const pendingCount = leaves.filter((l) => l.status === "pending").length;
  const shown = show === "pending" ? leaves.filter((l) => l.status === "pending") : leaves;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {isStaff && (
          <Button onClick={() => setOpen(true)}>
            <Plus className="h-4 w-4 mr-1" /> Record leave
          </Button>
        )}
        <Button variant={show === "all" ? "secondary" : "ghost"} size="sm" onClick={() => setShow("all")}>
          All
        </Button>
        <Button variant={show === "pending" ? "secondary" : "ghost"} size="sm" onClick={() => setShow("pending")}>
          Awaiting approval ({pendingCount})
        </Button>
      </div>
      {loading_leaves ? <Loading /> : shown.length === 0 ? (
        <Empty>{show === "pending" ? "No leave requests waiting." : "No instructor leave recorded."}</Empty>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Instructor</TableHead>
              <TableHead>From</TableHead>
              <TableHead>To</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Cover</TableHead>
              <TableHead>Status</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {shown.map((l) => (
              <TableRow key={l.id}>
                <TableCell>{instructorMap.get(l.instructor_id)?.full_name}</TableCell>
                <TableCell>{fmtDate(l.start_date)}</TableCell>
                <TableCell>{fmtDate(l.end_date)}</TableCell>
                <TableCell>
                  {label(l.type)}
                  {l.reason && <p className="text-xs text-muted-foreground">{l.reason}</p>}
                </TableCell>
                <TableCell>{l.cover_instructor_id ? instructorMap.get(l.cover_instructor_id)?.full_name : "—"}</TableCell>
                <TableCell>
                  <StatusBadge status={l.status} />
                  {l.decision_note && <p className="text-xs text-muted-foreground">{l.decision_note}</p>}
                </TableCell>
                <TableCell className="text-right whitespace-nowrap">
                  {isStaff && l.status === "pending" && (
                    <Button
                      size="sm"
                      onClick={() => {
                        setDecision({ note: "", cover: l.cover_instructor_id });
                        setDeciding(l);
                      }}
                    >
                      Review
                    </Button>
                  )}
                  {isStaff && l.status !== "pending" && (
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
      <Dialog open={!!deciding} onOpenChange={(o) => !o && setDeciding(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Leave request from {deciding ? instructorMap.get(deciding.instructor_id)?.full_name : ""}</DialogTitle>
          </DialogHeader>
          {deciding && (
            <p className="text-sm text-muted-foreground">
              {label(deciding.type)} · {fmtDate(deciding.start_date)} – {fmtDate(deciding.end_date)}
              {deciding.reason && ` · ${deciding.reason}`}
            </p>
          )}
          <Field label="Cover instructor (classes go to them on approval)">
            <RecordSelect
              value={decision.cover}
              onChange={(c) => setDecision({ ...decision, cover: c })}
              records={instructors.filter((i) => i.id !== deciding?.instructor_id && i.is_active)}
              render={(i) => i.full_name}
              allowNone="No cover"
            />
          </Field>
          <Field label="Note to the coach (optional)">
            <Input value={decision.note} maxLength={255} onChange={(e) => setDecision({ ...decision, note: e.target.value })} />
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
