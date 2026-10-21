import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, Building2, CalendarClock, CalendarDays, CalendarOff, CalendarRange, Clock, Sun, Users } from "lucide-react";
import { Page } from "@/components/layout/page";
import { BeltSwatch, Empty, Loading, RecordSelect, StatCard } from "@/components/common";
import { CoachContext, type CoachContextValue } from "@/components/coach/context";
import { CalendarTab } from "@/components/coach/calendar-tab";
import { ClassDayTab } from "@/components/coach/class-day-tab";
import { LeaveTab } from "@/components/coach/leave-tab";
import { ScheduleTab } from "@/components/coach/schedule-tab";
import { TodayTab } from "@/components/coach/today-tab";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/hooks/useAuth";
import { useBranch } from "@/hooks/useBranch";
import { useBelts, useInstructors, usePrograms } from "@/hooks/useLookups";
import { fmtDate, fmtDay, fmtTime, label } from "@/lib/format";
import { ApiError } from "@/lib/queryClient";
import type { CoachProfile } from "@/lib/types";

function initials(name: string) {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

function ProfileHeader({ coach }: { coach: CoachProfile }) {
  const { beltMap } = useBelts();
  const { programMap } = usePrograms();
  const belt = coach.belt_rank_id ? beltMap.get(coach.belt_rank_id) : undefined;
  const next = coach.next_session;
  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-5 flex flex-wrap items-center gap-4">
          <span className="flex h-14 w-14 items-center justify-center rounded-full brand-gradient text-lg font-semibold text-white" aria-hidden="true">
            {initials(coach.full_name)}
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-lg font-semibold text-foreground">{coach.full_name}</p>
            <p className="text-sm text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="inline-flex items-center gap-1">
                <Building2 className="h-3.5 w-3.5" aria-hidden="true" /> {coach.branch.name}
              </span>
              {belt && <BeltSwatch color={belt.color} name={belt.name} />}
              {coach.specialties && <span>{coach.specialties}</span>}
            </p>
          </div>
          <p className="text-sm text-muted-foreground">{fmtDay(coach.today)}</p>
        </CardContent>
      </Card>
      {coach.leave_today && (
        <div role="status" className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm">
          <AlertCircle className="h-4 w-4 mt-0.5 text-warning" aria-hidden="true" />
          <span>
            On {label(coach.leave_today.type).toLowerCase()} leave today ({fmtDate(coach.leave_today.start_date)} –{" "}
            {fmtDate(coach.leave_today.end_date)}). Your classes are handed to a cover.
          </span>
        </div>
      )}
      <div className="grid gap-4 grid-cols-2 lg:grid-cols-3">
        <StatCard title="Classes today" value={coach.classes_today} icon={Sun} />
        <StatCard title="Classes this week" value={coach.classes_this_week} icon={CalendarDays} tone="text-info" hint="Saturday to Friday" />
        <StatCard
          title="Next class"
          value={next ? fmtTime(next.start_time).slice(0, 5) : "—"}
          icon={Clock}
          tone="text-accent-purple"
          hint={
            next
              ? `${next.session_date === coach.today ? "Today" : fmtDay(next.session_date)} · ${programMap.get(next.program_id)?.name ?? ""}`
              : "Nothing scheduled"
          }
        />
      </div>
    </div>
  );
}

function Portal({ value }: { value: CoachContextValue }) {
  return (
    <CoachContext.Provider value={value}>
      <ProfileHeader coach={value.coach} />
      <Tabs defaultValue="today">
        <TabsList className="flex-wrap h-auto">
          <TabsTrigger value="today">
            <Sun className="h-4 w-4 mr-1" aria-hidden="true" /> Today
          </TabsTrigger>
          <TabsTrigger value="day">
            <Users className="h-4 w-4 mr-1" aria-hidden="true" /> Class day
          </TabsTrigger>
          <TabsTrigger value="schedule">
            <CalendarClock className="h-4 w-4 mr-1" aria-hidden="true" /> My schedule
          </TabsTrigger>
          <TabsTrigger value="calendar">
            <CalendarRange className="h-4 w-4 mr-1" aria-hidden="true" /> Calendar
          </TabsTrigger>
          <TabsTrigger value="leave">
            <CalendarOff className="h-4 w-4 mr-1" aria-hidden="true" /> Leave
          </TabsTrigger>
        </TabsList>
        <TabsContent value="today">
          <TodayTab />
        </TabsContent>
        <TabsContent value="day">
          <ClassDayTab />
        </TabsContent>
        <TabsContent value="schedule">
          <ScheduleTab />
        </TabsContent>
        <TabsContent value="calendar">
          <CalendarTab />
        </TabsContent>
        <TabsContent value="leave">
          <LeaveTab />
        </TabsContent>
      </Tabs>
    </CoachContext.Provider>
  );
}

function useCoachProfile(params: { instructor_id?: number }, enabled: boolean) {
  return useQuery<CoachProfile>({ queryKey: ["/api/coach/me", params], enabled, refetchInterval: 60_000 });
}

/** A coach's own portal. */
function OwnPortal() {
  const params = {};
  const { data: coach, isLoading, error } = useCoachProfile(params, true);
  if (isLoading) return <Loading />;
  if (!coach) {
    const msg =
      error instanceof ApiError && error.status === 404
        ? "Your account is not linked to a coach profile yet. Ask the operations manager to link it."
        : error?.message ?? "Your coach profile could not be loaded.";
    return <Empty icon={AlertCircle}>{msg}</Empty>;
  }
  return <Portal value={{ coach, params, isSelf: true }} />;
}

/** Staff open any coach's portal at the selected branch. */
function StaffPortal() {
  const { branchId } = useBranch();
  const { instructors } = useInstructors(branchId);
  const [picked, setPicked] = useState<number | null>(null);
  const active = instructors.filter((i) => i.is_active);
  const id = picked && active.some((i) => i.id === picked) ? picked : null;
  const params = id ? { instructor_id: id } : {};
  const { data: coach, isLoading } = useCoachProfile(params, id !== null);
  return (
    <div className="space-y-6">
      <div className="max-w-sm">
        <RecordSelect value={id} onChange={setPicked} records={active} render={(i) => i.full_name} placeholder="Choose a coach" />
      </div>
      {id === null ? (
        <Empty icon={Users}>Choose a coach to open their portal.</Empty>
      ) : isLoading || !coach ? (
        <Loading />
      ) : (
        <Portal value={{ coach, params, isSelf: false }} />
      )}
    </div>
  );
}

export default function Coach() {
  const { user } = useAuth();
  const isCoach = user?.role === "instructor";
  return (
    <Page
      title={isCoach ? "My portal" : "Coach portal"}
      subtitle={isCoach ? "Your classes, schedule and day at the academy" : undefined}
      needsBranch={!isCoach}
    >
      {isCoach ? <OwnPortal /> : <StaffPortal />}
    </Page>
  );
}
