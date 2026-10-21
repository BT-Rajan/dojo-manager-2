import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { addDays } from "date-fns";
import { CalendarX, ChevronLeft, ChevronRight, Plane } from "lucide-react";
import { AttendanceDialog } from "@/components/classes/attendance-dialog";
import { Empty, Loading } from "@/components/common";
import { DateInput } from "@/components/common/date-inputs";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { useInstructors } from "@/hooks/useLookups";
import { fmtDate, fmtDay, isoDate, label } from "@/lib/format";
import type { CoachDay, CoachSession } from "@/lib/types";
import { useCoach } from "./context";
import { CoachSessionCard } from "./session-card";

function shift(day: string, days: number): string {
  const [y, m, d] = day.split("-").map(Number);
  return isoDate(addDays(new Date(y, m - 1, d), days));
}

/** The whole branch's day: every class, who teaches it, and who is away. */
export function ClassDayTab() {
  const { coach, params } = useCoach();
  const { instructorMap } = useInstructors(coach.branch_id);
  const [day, setDay] = useState(coach.today);
  const [open, setOpen] = useState<CoachSession | null>(null);
  const { data, isLoading } = useQuery<CoachDay>({
    queryKey: ["/api/coach/day", { ...params, day }],
    enabled: !!day,
  });
  const sessions = data?.sessions ?? [];
  const mine = sessions.filter((s) => s.coach_role === "teaching" || s.coach_role === "covering");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="icon" onClick={() => setDay(shift(day, -1))} aria-label="Previous day">
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <DateInput value={day} onChange={(d) => d && setDay(d)} className="w-36" aria-label="Day" />
        <Button variant="outline" size="icon" onClick={() => setDay(shift(day, 1))} aria-label="Next day">
          <ChevronRight className="h-4 w-4" />
        </Button>
        {day !== coach.today && (
          <Button variant="ghost" onClick={() => setDay(coach.today)}>
            Today
          </Button>
        )}
        <span className="text-sm text-muted-foreground">
          {fmtDay(day)} · {coach.branch.name} · {sessions.length} classes, {mine.length} yours
        </span>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Classes</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {isLoading ? (
              <Loading rows={4} />
            ) : sessions.length === 0 ? (
              <Empty icon={CalendarX}>No classes at {coach.branch.name} on this day.</Empty>
            ) : (
              sessions.map((s) => (
                <CoachSessionCard key={s.id} session={s} instructorMap={instructorMap} onOpen={setOpen} showInstructor />
              ))
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Coaches away</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {(data?.on_leave ?? []).length === 0 ? (
              <Empty icon={Plane}>Everyone is in.</Empty>
            ) : (
              data!.on_leave.map((l) => (
                <div key={l.id} className="rounded border p-2">
                  <p className="font-medium">
                    {instructorMap.get(l.instructor_id)?.full_name ?? "Coach"}
                    {l.instructor_id === coach.id && <span className="ml-1 text-primary">(you)</span>}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {label(l.type)} · {fmtDate(l.start_date)} – {fmtDate(l.end_date)}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Cover: {l.cover_instructor_id ? instructorMap.get(l.cover_instructor_id)?.full_name : "none"}
                  </p>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>
      <Dialog open={!!open} onOpenChange={(o) => !o && setOpen(null)}>
        {open && <AttendanceDialog session={open} onClose={() => setOpen(null)} />}
      </Dialog>
    </div>
  );
}
