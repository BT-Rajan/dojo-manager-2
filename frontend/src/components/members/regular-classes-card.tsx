import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarCheck, Plus } from "lucide-react";
import { Empty, Field, RecordSelect } from "@/components/common";
import { DateInput } from "@/components/common/date-inputs";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useApiMutation } from "@/hooks/useApiMutation";
import { useAuth } from "@/hooks/useAuth";
import { usePrograms } from "@/hooks/useLookups";
import { WEEKDAYS, fmtDate, fmtTime, isoDate } from "@/lib/format";
import { api } from "@/lib/queryClient";
import type { Enrollment, Member, Schedule } from "@/lib/types";

/** A member's regular weekly classes: a place every week without booking. */
export function RegularClassesCard({ member }: { member: Member }) {
  const { isStaff } = useAuth();
  const { programMap } = usePrograms();
  const url = `/api/members/${member.id}/enrollments`;
  const { data: rows = [] } = useQuery<Enrollment[]>({ queryKey: [url] });
  const { data: timetable = [] } = useQuery<Schedule[]>({
    queryKey: ["/api/schedules", { branch_id: member.branch_id }],
    enabled: isStaff,
  });
  const [open, setOpen] = useState(false);
  const [scheduleId, setScheduleId] = useState<number | null>(null);
  const [start, setStart] = useState(isoDate());
  const affected = [url, "/api/sessions", "/api/coach", "/api/dashboard"];
  const enroll = useApiMutation(
    () => api(url, { method: "POST", body: { schedule_id: scheduleId, start_date: start || null } }),
    { invalidate: affected, success: "Regular class added", onSuccess: () => setOpen(false) },
  );
  const end = useApiMutation((id: number) => api(`/api/enrollments/${id}/end`, { method: "POST", body: {} }), {
    invalidate: affected,
    success: "Regular class ended today",
  });
  const describe = (s: { weekday: number; start_time: string; end_time: string; program_id: number; title: string | null }) =>
    `${WEEKDAYS[s.weekday]} ${fmtTime(s.start_time).slice(0, 5)}–${fmtTime(s.end_time).slice(0, 5)} · ${s.title ?? programMap.get(s.program_id)?.name ?? ""}`;
  const taken = new Set(rows.filter((r) => r.end_date === null).map((r) => r.schedule_id));
  const active = rows.filter((r) => r.is_active);
  const past = rows.filter((r) => !r.is_active);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between gap-2 text-base">
          Regular classes
          {isStaff && (
            <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
              <Plus className="h-4 w-4 mr-1" /> Add
            </Button>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {active.length === 0 ? (
          <Empty icon={CalendarCheck}>No regular weekly class.</Empty>
        ) : (
          active.map((r) => (
            <div key={r.id} className="flex items-center justify-between gap-2 rounded border p-2">
              <div>
                <p className="font-medium">{describe(r)}</p>
                <p className="text-xs text-muted-foreground">
                  Since {fmtDate(r.start_date)}
                  {r.end_date && ` · until ${fmtDate(r.end_date)}`}
                </p>
              </div>
              {isStaff && r.end_date === null && (
                <Button size="sm" variant="ghost" onClick={() => end.mutate(r.id)}>
                  End
                </Button>
              )}
            </div>
          ))
        )}
        {past.length > 0 && (
          <details className="text-xs text-muted-foreground">
            <summary className="cursor-pointer">Earlier regular classes ({past.length})</summary>
            <ul className="mt-1 space-y-0.5">
              {past.map((r) => (
                <li key={r.id}>
                  {describe(r)} · {fmtDate(r.start_date)} – {fmtDate(r.end_date)}
                </li>
              ))}
            </ul>
          </details>
        )}
        <p className="text-xs text-muted-foreground">Regular members hold a place every week and are on each class roster.</p>
      </CardContent>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add a regular weekly class</DialogTitle>
          </DialogHeader>
          <Field label="Weekly class">
            <RecordSelect
              value={scheduleId}
              onChange={setScheduleId}
              records={timetable.filter((s) => !taken.has(s.id))}
              render={describe}
              placeholder="Choose from the timetable"
            />
          </Field>
          <Field label="From">
            <DateInput value={start} onChange={setStart} />
          </Field>
          <Button disabled={!scheduleId || !start || enroll.isPending} onClick={() => enroll.mutate(undefined)}>
            Save
          </Button>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
