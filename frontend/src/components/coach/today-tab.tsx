import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarCheck } from "lucide-react";
import { AttendanceDialog } from "@/components/classes/attendance-dialog";
import { Empty, Loading } from "@/components/common";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { useInstructors } from "@/hooks/useLookups";
import { fmtDay } from "@/lib/format";
import type { CoachSession } from "@/lib/types";
import { useCoach } from "./context";
import { CoachSessionCard, sessionTiming } from "./session-card";

/** Today's classes: take attendance for the one in progress, see what is next. */
export function TodayTab() {
  const { coach, params } = useCoach();
  const { instructorMap } = useInstructors(coach.branch_id);
  const [open, setOpen] = useState<CoachSession | null>(null);
  const { data: sessions = [], isLoading } = useQuery<CoachSession[]>({
    queryKey: ["/api/coach/today", params],
    refetchInterval: 60_000,
  });
  const active = sessions.filter((s) => sessionTiming(s) !== "past");
  const done = sessions.filter((s) => sessionTiming(s) === "past");

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">{fmtDay(coach.today)}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {isLoading ? (
            <Loading rows={3} />
          ) : sessions.length === 0 ? (
            <Empty icon={CalendarCheck}>No classes for you today.</Empty>
          ) : (
            <>
              {active.map((s) => (
                <CoachSessionCard key={s.id} session={s} instructorMap={instructorMap} onOpen={setOpen} />
              ))}
              {done.length > 0 && (
                <div className="space-y-3 pt-2">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Finished</p>
                  {done.map((s) => (
                    <CoachSessionCard key={s.id} session={s} instructorMap={instructorMap} onOpen={setOpen} />
                  ))}
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
      <Dialog open={!!open} onOpenChange={(o) => !o && setOpen(null)}>
        {open && <AttendanceDialog session={open} onClose={() => setOpen(null)} />}
      </Dialog>
    </div>
  );
}
