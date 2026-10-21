import { ClipboardCheck, Users } from "lucide-react";
import { StatusBadge } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { usePrograms } from "@/hooks/useLookups";
import { academyNow, isoDate, fmtTime } from "@/lib/format";
import type { CoachSession, Instructor } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Live state of a class against the academy clock. */
export function sessionTiming(s: CoachSession): "past" | "now" | "upcoming" {
  const today = isoDate();
  if (s.session_date < today) return "past";
  if (s.session_date > today) return "upcoming";
  const now = academyNow();
  if (now >= fmtTime(s.end_time)) return "past";
  return now >= fmtTime(s.start_time) ? "now" : "upcoming";
}

export function RoleBadge({ session, instructorMap }: { session: CoachSession; instructorMap: Map<number, Instructor> }) {
  if (session.coach_role === "covering") {
    const who = session.original_instructor_id ? instructorMap.get(session.original_instructor_id)?.full_name : null;
    return <Badge className="border-0 bg-warning/15 text-warning">Covering{who ? ` for ${who}` : ""}</Badge>;
  }
  if (session.coach_role === "covered") {
    const who = session.instructor_id ? instructorMap.get(session.instructor_id)?.full_name : null;
    return (
      <Badge variant="outline" className="border-0 bg-muted text-foreground/80">
        {who ? `Covered by ${who}` : "Needs a cover"}
      </Badge>
    );
  }
  return null;
}

/** One class in the coach portal: time, programme, places and an attendance action. */
export function CoachSessionCard({
  session: s,
  instructorMap,
  onOpen,
  showInstructor = false,
}: {
  session: CoachSession;
  instructorMap: Map<number, Instructor>;
  onOpen?: (s: CoachSession) => void;
  showInstructor?: boolean;
}) {
  const { programMap } = usePrograms();
  const timing = sessionTiming(s);
  const cancelled = s.status === "cancelled";
  const mine = s.coach_role === "teaching" || s.coach_role === "covering";
  return (
    <div
      className={cn(
        "rounded-lg border p-3 space-y-2 transition-colors",
        mine && "border-primary/40 bg-primary/5",
        timing === "now" && !cancelled && "ring-2 ring-primary",
        (cancelled || s.coach_role === "covered") && "opacity-70",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-medium tabular">
            {fmtTime(s.start_time)}–{fmtTime(s.end_time)}
            {timing === "now" && !cancelled && (
              <span className="ml-2 inline-flex items-center gap-1 text-xs font-semibold text-primary">
                <span className="h-2 w-2 animate-pulse rounded-full bg-primary" aria-hidden="true" /> In progress
              </span>
            )}
          </p>
          <p className="text-sm text-foreground">
            {programMap.get(s.program_id)?.name ?? "Class"}
            {s.title && <span className="text-muted-foreground"> · {s.title}</span>}
          </p>
          {showInstructor && (
            <p className="text-xs text-muted-foreground">
              {s.instructor_id ? instructorMap.get(s.instructor_id)?.full_name : "No instructor"}
              {mine && <span className="ml-1 font-semibold text-primary">(you)</span>}
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <RoleBadge session={s} instructorMap={instructorMap} />
          {s.status !== "scheduled" && <StatusBadge status={s.status} />}
        </div>
      </div>
      {cancelled && s.change_reason && <p className="text-xs text-destructive">Cancelled: {s.change_reason}</p>}
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span className="flex items-center gap-1 text-muted-foreground tabular">
          <Users className="h-4 w-4" aria-hidden="true" /> {s.booked}/{s.capacity} booked · {s.attended} present
        </span>
        {onOpen && mine && !cancelled && (
          <Button size="sm" variant={timing === "now" ? "default" : "outline"} onClick={() => onOpen(s)}>
            <ClipboardCheck className="h-4 w-4 mr-1" /> {timing === "past" ? "Review attendance" : "Attendance"}
          </Button>
        )}
      </div>
    </div>
  );
}
