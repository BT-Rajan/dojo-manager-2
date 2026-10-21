import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { addDays, addMonths, endOfMonth, format, startOfMonth, startOfWeek } from "date-fns";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { AttendanceDialog } from "@/components/classes/attendance-dialog";
import { Empty } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { useInstructors } from "@/hooks/useLookups";
import { WEEKDAYS, fmtDay, isoDate, label } from "@/lib/format";
import type { CoachSession, Leave } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useCoach } from "./context";
import { CoachSessionCard } from "./session-card";

const HEAD = [6, 7, 1, 2, 3, 4, 5]; // Saturday first, as academy weeks run

function leaveOn(leaves: Leave[], day: string): Leave | undefined {
  return leaves.find((l) => l.start_date <= day && l.end_date >= day && (l.status === "approved" || l.status === "pending"));
}

/** A month at a glance: classes, covers and leave per day; pick a day for its classes. */
export function CalendarTab() {
  const { coach, params } = useCoach();
  const { instructorMap } = useInstructors(coach.branch_id);
  const [month, setMonth] = useState(() => {
    const [y, m] = coach.today.split("-").map(Number);
    return new Date(y, m - 1, 1);
  });
  const [picked, setPicked] = useState(coach.today);
  const [open, setOpen] = useState<CoachSession | null>(null);
  const first = startOfMonth(month);
  const last = endOfMonth(month);
  const { data: sessions = [] } = useQuery<CoachSession[]>({
    queryKey: ["/api/coach/sessions", { ...params, date_from: isoDate(first), date_to: isoDate(last) }],
  });
  const { data: leaves = [] } = useQuery<Leave[]>({ queryKey: ["/api/coach/leaves", params] });

  const cells = useMemo(() => {
    const start = startOfWeek(first, { weekStartsOn: 6 });
    const out: Date[] = [];
    for (let d = start; d <= last || out.length % 7 !== 0; d = addDays(d, 1)) out.push(d);
    return out;
  }, [first.getTime(), last.getTime()]);
  const byDay = useMemo(() => {
    const m = new Map<string, CoachSession[]>();
    for (const s of sessions) m.set(s.session_date, [...(m.get(s.session_date) ?? []), s]);
    return m;
  }, [sessions]);
  const dayList = byDay.get(picked) ?? [];
  const pickedLeave = leaveOn(leaves, picked);
  const teaching = sessions.filter((s) => s.coach_role !== "covered" && s.status !== "cancelled").length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="icon" onClick={() => setMonth(addMonths(month, -1))} aria-label="Previous month">
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="w-36 text-center font-medium">{format(month, "MMMM yyyy")}</span>
        <Button variant="outline" size="icon" onClick={() => setMonth(addMonths(month, 1))} aria-label="Next month">
          <ChevronRight className="h-4 w-4" />
        </Button>
        <span className="text-sm text-muted-foreground">{teaching} classes to teach this month</span>
      </div>
      <Card>
        <CardContent className="p-3 sm:p-4">
          <div className="grid grid-cols-7 gap-1 text-center text-xs font-medium text-muted-foreground">
            {HEAD.map((d) => (
              <div key={d} className="py-1">
                <span className="hidden sm:inline">{WEEKDAYS[d].slice(0, 3)}</span>
                <span className="sm:hidden">{WEEKDAYS[d][0]}</span>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1">
            {cells.map((d) => {
              const iso = isoDate(d);
              const list = byDay.get(iso) ?? [];
              const mine = list.filter((s) => s.coach_role === "teaching" && s.status !== "cancelled").length;
              const covering = list.filter((s) => s.coach_role === "covering" && s.status !== "cancelled").length;
              const leave = leaveOn(leaves, iso);
              const inMonth = d.getMonth() === month.getMonth();
              return (
                <button
                  key={iso}
                  onClick={() => setPicked(iso)}
                  aria-pressed={picked === iso}
                  aria-label={`${fmtDay(iso)}: ${mine + covering} classes${leave ? `, ${leave.status} leave` : ""}`}
                  className={cn(
                    "min-h-16 rounded-md border p-1.5 text-left text-xs transition-colors hover:bg-muted/60 sm:min-h-20",
                    !inMonth && "opacity-40",
                    leave?.status === "approved" && "bg-warning/10 border-warning/40",
                    leave?.status === "pending" && "border-dashed border-warning",
                    picked === iso && "ring-2 ring-primary",
                  )}
                >
                  <span className={cn("font-semibold tabular", iso === coach.today && "rounded bg-primary px-1 text-primary-foreground")}>
                    {d.getDate()}
                  </span>
                  <div className="mt-1 space-y-0.5">
                    {mine > 0 && <p className="truncate text-primary">{mine} class{mine > 1 ? "es" : ""}</p>}
                    {covering > 0 && <p className="truncate text-warning">{covering} cover</p>}
                    {leave && <p className="truncate text-warning">{leave.status === "pending" ? "Leave?" : "Leave"}</p>}
                  </div>
                </button>
              );
            })}
          </div>
          <div className="mt-3 flex flex-wrap gap-4 text-xs text-muted-foreground">
            <span className="flex items-center gap-1"><span className="h-3 w-3 rounded border border-warning/40 bg-warning/10" /> Approved leave</span>
            <span className="flex items-center gap-1"><span className="h-3 w-3 rounded border border-dashed border-warning" /> Leave awaiting approval</span>
            <span className="flex items-center gap-1"><span className="h-3 w-3 rounded bg-primary" /> Today</span>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">{fmtDay(picked)}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {pickedLeave && (
            <p className="text-sm text-warning">
              {label(pickedLeave.type)} leave ({pickedLeave.status})
            </p>
          )}
          {dayList.length === 0 ? (
            <Empty>No classes for you on this day.</Empty>
          ) : (
            dayList.map((s) => <CoachSessionCard key={s.id} session={s} instructorMap={instructorMap} onOpen={setOpen} />)
          )}
        </CardContent>
      </Card>
      <Dialog open={!!open} onOpenChange={(o) => !o && setOpen(null)}>
        {open && <AttendanceDialog session={open} onClose={() => setOpen(null)} />}
      </Dialog>
    </div>
  );
}
