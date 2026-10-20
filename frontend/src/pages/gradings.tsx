import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Plus } from "lucide-react";
import { Page } from "@/components/layout/page";
import { BeltSwatch, Empty, EnumSelect, Field, Loading, RecordSelect, StatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApiMutation } from "@/hooks/useApiMutation";
import { useAuth } from "@/hooks/useAuth";
import { useBranch } from "@/hooks/useBranch";
import { useBelts, useInstructors } from "@/hooks/useLookups";
import { fmtDate, isoDate } from "@/lib/format";
import { api } from "@/lib/queryClient";
import type { Belt, Eligibility, GradingEvent, GradingOutcome, GradingResult, Member, Seminar } from "@/lib/types";
import { DateInput } from "@/components/common/date-inputs";

function beltName(beltMap: Map<number, Belt>, id: number | null, stripes = 0) {
  const b = id ? beltMap.get(id) : undefined;
  if (!b) return <span className="text-muted-foreground/70">No belt</span>;
  return <BeltSwatch color={b.color} name={`${b.name}${stripes ? ` +${stripes}` : ""}`} />;
}

function useEligibility() {
  const { branchId } = useBranch();
  return useQuery<Eligibility[]>({
    queryKey: ["/api/gradings-eligibility", { branch_id: branchId }],
    enabled: branchId !== null,
  }).data ?? [];
}

function EventDialog({ event }: { event: GradingEvent }) {
  const { isStaff } = useAuth();
  const { belts, beltMap } = useBelts();
  const eligibility = useEligibility();
  const url = `/api/gradings/${event.id}/results`;
  const { data: results = [], isLoading: loading_results } = useQuery<GradingResult[]>({ queryKey: [url] });
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const names = new Map(eligibility.map((e) => [e.member_id, e.member_name]));
  const inEvent = new Set(results.map((r) => r.member_id));
  const open = event.status === "planned";

  const record = useApiMutation(
    (entries: Record<string, unknown>[]) => api(url, { method: "POST", body: { entries } }),
    { invalidate: [url] },
  );
  const finalize = useApiMutation(() => api(`/api/gradings/${event.id}/finalize`, { method: "POST" }), {
    invalidate: ["/api/gradings", "/api/members"],
    success: "Grading finalised — passing students promoted",
  });

  return (
    <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
      <DialogHeader>
        <DialogTitle>
          {event.title} · {fmtDate(event.event_date)}
        </DialogTitle>
      </DialogHeader>
      {loading_results ? <Loading /> : results.length === 0 ? (
        <Empty>No candidates yet.</Empty>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Student</TableHead>
              <TableHead>From</TableHead>
              <TableHead>To</TableHead>
              <TableHead className="w-36">Outcome</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {results.map((r) => (
              <TableRow key={r.id}>
                <TableCell>{names.get(r.member_id) ?? `#${r.member_id}`}</TableCell>
                <TableCell>{beltName(beltMap, r.from_rank_id, r.from_stripes)}</TableCell>
                <TableCell>
                  {open ? (
                    <div className="flex gap-1">
                      <RecordSelect
                        value={r.to_rank_id}
                        onChange={(id) => record.mutate([{ member_id: r.member_id, to_rank_id: id }])}
                        records={belts}
                        render={(b) => b.name}
                      />
                      <Input
                        type="number"
                        min={0}
                        max={4}
                        className="w-16"
                        aria-label="Stripes"
                        defaultValue={r.to_stripes}
                        onBlur={(e) => record.mutate([{ member_id: r.member_id, to_stripes: Number(e.target.value) }])}
                      />
                    </div>
                  ) : (
                    beltName(beltMap, r.to_rank_id, r.to_stripes)
                  )}
                </TableCell>
                <TableCell>
                  {open ? (
                    <EnumSelect
                      value={r.outcome}
                      onChange={(o) => record.mutate([{ member_id: r.member_id, outcome: o as GradingOutcome }])}
                      options={["pending", "pass", "fail", "deferred"]}
                    />
                  ) : (
                    <StatusBadge status={r.outcome} />
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {open && (
        <div className="space-y-2 border-t pt-4">
          <p className="text-sm font-medium">Add candidates</p>
          <div className="max-h-48 overflow-y-auto space-y-1">
            {eligibility
              .filter((e) => !inEvent.has(e.member_id))
              .map((e) => (
                <label key={e.member_id} className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={picked.has(e.member_id)}
                    onCheckedChange={(c) => {
                      const next = new Set(picked);
                      if (c) next.add(e.member_id);
                      else next.delete(e.member_id);
                      setPicked(next);
                    }}
                  />
                  {e.member_name}
                  <span className="text-muted-foreground/70">
                    seminars {e.seminar_points}/{e.seminars_required} · {e.classes_since_promotion} classes
                  </span>
                  {e.seminar_requirement_met && <CheckCircle2 className="h-4 w-4 text-success" />}
                </label>
              ))}
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              disabled={picked.size === 0 || record.isPending}
              onClick={() => {
                record.mutate([...picked].map((member_id) => ({ member_id })));
                setPicked(new Set());
              }}
            >
              Add {picked.size || ""} selected
            </Button>
            {isStaff && (
              <Button disabled={results.length === 0 || finalize.isPending} onClick={() => finalize.mutate(undefined)}>
                Finalise grading
              </Button>
            )}
          </div>
        </div>
      )}
    </DialogContent>
  );
}

function GradingsTab() {
  const { branchId } = useBranch();
  const { isStaff } = useAuth();
  const { instructors, instructorMap } = useInstructors(branchId);
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<GradingEvent | null>(null);
  const [f, setF] = useState({ title: "", event_date: isoDate() });
  const [examiner, setExaminer] = useState<number | null>(null);
  const { data: events = [], isLoading: loading_events } = useQuery<GradingEvent[]>({
    queryKey: ["/api/gradings", { branch_id: branchId }],
    enabled: branchId !== null,
  });
  const create = useApiMutation(
    () => api("/api/gradings", { method: "POST", body: { ...f, branch_id: branchId, examiner_instructor_id: examiner } }),
    { invalidate: ["/api/gradings"], success: "Grading scheduled", onSuccess: () => setCreating(false) },
  );

  return (
    <div className="space-y-4">
      {isStaff && (
        <Button onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4 mr-1" /> Schedule grading
        </Button>
      )}
      {loading_events ? <Loading /> : events.length === 0 ? (
        <Empty>No gradings yet.</Empty>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Date</TableHead>
              <TableHead>Title</TableHead>
              <TableHead>Examiner</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {events.map((e) => (
              <TableRow key={e.id} className="cursor-pointer" onClick={() => setSelected(e)}>
                <TableCell>{fmtDate(e.event_date)}</TableCell>
                <TableCell className="text-brand">{e.title}</TableCell>
                <TableCell>{e.examiner_instructor_id ? instructorMap.get(e.examiner_instructor_id)?.full_name : "—"}</TableCell>
                <TableCell>
                  <StatusBadge status={e.status} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <Dialog open={!!selected} onOpenChange={(o) => !o && setSelected(null)}>
        {selected && <EventDialog event={selected} />}
      </Dialog>
      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Schedule grading</DialogTitle>
          </DialogHeader>
          <Field label="Title">
            <Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="e.g. Quarterly belt test" />
          </Field>
          <Field label="Date">
            <DateInput value={f.event_date} onChange={(d) => setF({ ...f, event_date: d })} />
          </Field>
          <Field label="Examiner">
            <RecordSelect value={examiner} onChange={setExaminer} records={instructors} render={(i) => i.full_name} allowNone="To be confirmed" />
          </Field>
          <Button disabled={!f.title || !f.event_date || create.isPending} onClick={() => create.mutate(undefined)}>
            Save
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function ReadinessTab() {
  const { beltMap } = useBelts();
  const rows = useEligibility();
  return rows.length === 0 ? (
    <Empty>No active students.</Empty>
  ) : (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Student</TableHead>
          <TableHead>Current</TableHead>
          <TableHead>Next</TableHead>
          <TableHead>Seminar points</TableHead>
          <TableHead>Classes since promotion</TableHead>
          <TableHead>Last promoted</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={r.member_id}>
            <TableCell>{r.member_name}</TableCell>
            <TableCell>{beltName(beltMap, r.belt_rank_id, r.stripes)}</TableCell>
            <TableCell>{beltName(beltMap, r.next_rank_id)}</TableCell>
            <TableCell className={r.seminar_requirement_met ? "text-success" : "text-warning"}>
              {r.seminar_points} / {r.seminars_required}
            </TableCell>
            <TableCell>{r.classes_since_promotion}</TableCell>
            <TableCell>{fmtDate(r.last_promoted_on)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function SeminarsTab() {
  const { branchId } = useBranch();
  const { isStaff } = useAuth();
  const { instructors } = useInstructors(branchId);
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<Seminar | null>(null);
  const [f, setF] = useState({ title: "Self-Defence & Traditional Seminar", seminar_date: isoDate(), points: "1" });
  const [instructorId, setInstructorId] = useState<number | null>(null);
  const [q, setQ] = useState("");
  const { data: seminars = [], isLoading: loading_seminars } = useQuery<Seminar[]>({
    queryKey: ["/api/seminars", { branch_id: branchId }],
    enabled: branchId !== null,
  });
  const attendeesUrl = selected ? `/api/seminars/${selected.id}/attendees` : "";
  const { data: attendees = [] } = useQuery<number[]>({ queryKey: [attendeesUrl], enabled: !!selected });
  const { data: found = [] } = useQuery<Member[]>({
    queryKey: ["/api/members", { branch_id: branchId, q: q.trim(), status: "active", limit: 10 }],
    enabled: !!selected && q.trim().length >= 2,
  });
  const create = useApiMutation(
    () =>
      api("/api/seminars", {
        method: "POST",
        body: { ...f, points: Number(f.points), branch_id: branchId, instructor_id: instructorId },
      }),
    { invalidate: ["/api/seminars"], success: "Seminar added", onSuccess: () => setCreating(false) },
  );
  const addAttendee = useApiMutation(
    (memberId: number) => api(attendeesUrl, { method: "POST", body: { member_ids: [memberId] } }),
    { invalidate: [attendeesUrl, "/api/seminars", "/api/gradings-eligibility"] },
  );

  return (
    <div className="space-y-4">
      {isStaff && (
        <Button onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4 mr-1" /> Add seminar
        </Button>
      )}
      {loading_seminars ? <Loading /> : seminars.length === 0 ? (
        <Empty>No seminars yet.</Empty>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {seminars.map((s) => (
            <Card key={s.id} className="cursor-pointer card-hover" onClick={() => setSelected(s)}>
              <CardContent className="p-4">
                <p className="font-medium">{s.title}</p>
                <p className="text-sm text-muted-foreground">
                  {fmtDate(s.seminar_date)} · {s.points} point(s) · {s.attendee_count} attended
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      <Dialog open={!!selected} onOpenChange={(o) => !o && setSelected(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{selected?.title}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">{attendees.length} attendee(s) recorded</p>
          <Input placeholder="Find student (name or phone)" value={q} onChange={(e) => setQ(e.target.value)} />
          {found.map((m) => (
            <div key={m.id} className="flex items-center justify-between text-sm border rounded p-2">
              <span>{m.full_name}</span>
              {attendees.includes(m.id) ? (
                <CheckCircle2 className="h-4 w-4 text-success" />
              ) : (
                <Button size="sm" onClick={() => addAttendee.mutate(m.id)}>
                  Mark attended
                </Button>
              )}
            </div>
          ))}
        </DialogContent>
      </Dialog>
      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add seminar</DialogTitle>
          </DialogHeader>
          <Field label="Title">
            <Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} />
          </Field>
          <Field label="Date">
            <DateInput value={f.seminar_date} onChange={(d) => setF({ ...f, seminar_date: d })} />
          </Field>
          <Field label="Points awarded">
            <Input type="number" min={0} max={10} value={f.points} onChange={(e) => setF({ ...f, points: e.target.value })} />
          </Field>
          <Field label="Instructor">
            <RecordSelect value={instructorId} onChange={setInstructorId} records={instructors} render={(i) => i.full_name} allowNone="—" />
          </Field>
          <Button disabled={!f.title || create.isPending} onClick={() => create.mutate(undefined)}>
            Save
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function Gradings() {
  return (
    <Page title="Gradings & seminars">
      <Tabs defaultValue="gradings">
        <TabsList>
          <TabsTrigger value="gradings">Belt gradings</TabsTrigger>
          <TabsTrigger value="readiness">Promotion readiness</TabsTrigger>
          <TabsTrigger value="seminars">Seminars</TabsTrigger>
        </TabsList>
        <TabsContent value="gradings">
          <GradingsTab />
        </TabsContent>
        <TabsContent value="readiness">
          <ReadinessTab />
        </TabsContent>
        <TabsContent value="seminars">
          <SeminarsTab />
        </TabsContent>
      </Tabs>
    </Page>
  );
}
