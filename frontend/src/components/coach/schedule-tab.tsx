import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { addDays, startOfWeek } from "date-fns";
import { CalendarClock, ChevronLeft, ChevronRight, Clock, Repeat, UserCheck, Users } from "lucide-react";
import { AttendanceDialog } from "@/components/classes/attendance-dialog";
import { Empty, Loading, StatCard } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useInstructors, usePrograms } from "@/hooks/useLookups";
import { WEEKDAYS, dmy, fmtDay, fmtTime, isoDate } from "@/lib/format";
import type { CoachSession, Schedule } from "@/lib/types";
import { useCoach } from "./context";
import { CoachSessionCard } from "./session-card";

const WEEK_ORDER = [6, 7, 1, 2, 3, 4, 5]; // Saturday first

function minutes(s: CoachSession): number {
  const [sh, sm] = s.start_time.split(":").map(Number);
  const [eh, em] = s.end_time.split(":").map(Number);
  return eh * 60 + em - (sh * 60 + sm);
}

/** The coach's week (Saturday to Friday) and their standing weekly timetable. */
export function ScheduleTab() {
  const { coach, params } = useCoach();
  const { programMap } = usePrograms();
  const { instructorMap } = useInstructors(coach.branch_id);
  const [weekStart, setWeekStart] = useState(() => {
    const [y, m, d] = coach.today.split("-").map(Number);
    return startOfWeek(new Date(y, m - 1, d), { weekStartsOn: 6 });
  });
  const [open, setOpen] = useState<CoachSession | null>(null);
  const from = isoDate(weekStart);
  const to = isoDate(addDays(weekStart, 6));
  const { data: sessions = [], isLoading } = useQuery<CoachSession[]>({
    queryKey: ["/api/coach/sessions", { ...params, date_from: from, date_to: to }],
  });
  const { data: timetable = [] } = useQuery<Schedule[]>({ queryKey: ["/api/coach/timetable", params] });

  const teaching = sessions.filter((s) => s.coach_role !== "covered" && s.status !== "cancelled");
  const days = useMemo(
    () => Array.from({ length: 7 }, (_, i) => isoDate(addDays(weekStart, i))),
    [weekStart],
  );
  const hours = teaching.reduce((t, s) => t + minutes(s), 0) / 60;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="icon" onClick={() => setWeekStart(addDays(weekStart, -7))} aria-label="Previous week">
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="font-medium tabular">
          {dmy(weekStart)} – {dmy(addDays(weekStart, 6))}
        </span>
        <Button variant="outline" size="icon" onClick={() => setWeekStart(addDays(weekStart, 7))} aria-label="Next week">
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
      <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
        <StatCard title="Classes" value={teaching.length} icon={CalendarClock} />
        <StatCard title="Teaching hours" value={hours.toFixed(1)} icon={Clock} tone="text-info" />
        <StatCard title="Students booked" value={teaching.reduce((t, s) => t + s.booked, 0)} icon={Users} tone="text-accent-purple" />
        <StatCard
          title="Covering"
          value={sessions.filter((s) => s.coach_role === "covering").length}
          icon={UserCheck}
          tone="text-warning"
          hint={`${sessions.filter((s) => s.coach_role === "covered").length} of yours covered`}
        />
      </div>
      {isLoading ? (
        <Loading />
      ) : sessions.length === 0 ? (
        <Empty icon={CalendarClock}>No classes for you this week.</Empty>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {days
            .filter((d) => sessions.some((s) => s.session_date === d))
            .map((d) => (
              <Card key={d} className={d === coach.today ? "ring-2 ring-primary/50" : undefined}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">
                    {fmtDay(d)}
                    {d === coach.today && <span className="ml-2 text-xs font-semibold text-primary">Today</span>}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {sessions
                    .filter((s) => s.session_date === d)
                    .map((s) => (
                      <CoachSessionCard key={s.id} session={s} instructorMap={instructorMap} onOpen={setOpen} />
                    ))}
                </CardContent>
              </Card>
            ))}
        </div>
      )}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <Repeat className="h-4 w-4" aria-hidden="true" /> Weekly timetable
          </CardTitle>
        </CardHeader>
        <CardContent>
          {timetable.length === 0 ? (
            <Empty>No weekly classes are assigned to you.</Empty>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Day</TableHead>
                  <TableHead>Time</TableHead>
                  <TableHead>Programme</TableHead>
                  <TableHead>Room</TableHead>
                  <TableHead className="text-right">Capacity</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {[...timetable]
                  .sort((a, b) => WEEK_ORDER.indexOf(a.weekday) - WEEK_ORDER.indexOf(b.weekday) || a.start_time.localeCompare(b.start_time))
                  .map((t) => (
                    <TableRow key={t.id}>
                      <TableCell>{WEEKDAYS[t.weekday]}</TableCell>
                      <TableCell className="tabular">
                        {fmtTime(t.start_time)}–{fmtTime(t.end_time)}
                      </TableCell>
                      <TableCell>
                        {programMap.get(t.program_id)?.name}
                        {t.title && <span className="text-muted-foreground"> · {t.title}</span>}
                      </TableCell>
                      <TableCell>{t.room ?? "—"}</TableCell>
                      <TableCell className="text-right tabular">{t.capacity}</TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <Dialog open={!!open} onOpenChange={(o) => !o && setOpen(null)}>
        {open && <AttendanceDialog session={open} onClose={() => setOpen(null)} />}
      </Dialog>
    </div>
  );
}
