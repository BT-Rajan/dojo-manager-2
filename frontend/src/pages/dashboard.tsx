import { useQuery } from "@tanstack/react-query";
import { Link } from "wouter";
import {
  AlertTriangle,
  CalendarClock,
  MessageSquareWarning,
  Package,
  UserCheck,
  UserPlus,
  Users,
  Wallet,
} from "lucide-react";
import { Page } from "@/components/layout/page";
import { Empty, StatCard, StatusBadge } from "@/components/common";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAuth } from "@/hooks/useAuth";
import { useBranch } from "@/hooks/useBranch";
import { useInstructors } from "@/hooks/useLookups";
import { fmtDate, fmtTime, kd } from "@/lib/format";
import type { Dashboard as DashboardData, Membership } from "@/lib/types";

export default function Dashboard() {
  const { branchId } = useBranch();
  const { isStaff } = useAuth();
  const { instructorMap } = useInstructors(branchId);
  const { data } = useQuery<DashboardData>({
    queryKey: ["/api/dashboard", { branch_id: branchId }],
    enabled: branchId !== null,
  });
  const { data: expiring = [] } = useQuery<Membership[]>({
    queryKey: ["/api/memberships/expiring", { branch_id: branchId, days: 5 }],
    enabled: branchId !== null && isStaff,
  });

  return (
    <Page title="Dashboard">
      <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
        <StatCard title="Active members" value={data?.active_members ?? "—"} icon={Users} />
        <StatCard
          title="New this month"
          value={data?.new_members_this_month ?? "—"}
          icon={UserCheck}
          tone="text-success"
        />
        <StatCard
          title="Expiring ≤ 5 days"
          value={data?.expiring_within_5_days ?? "—"}
          icon={CalendarClock}
          tone="text-warning"
          hint={data ? `${data.expired_last_30_days} expired in last 30 days` : undefined}
        />
        <StatCard title="Open leads" value={data?.open_leads ?? "—"} icon={UserPlus} tone="text-accent-purple" />
        <StatCard
          title="Open incidents"
          value={data?.open_incidents ?? "—"}
          icon={AlertTriangle}
          tone="text-destructive"
        />
        <StatCard
          title="Open complaints"
          value={data?.open_complaints ?? "—"}
          icon={MessageSquareWarning}
          tone="text-destructive"
        />
        <StatCard title="Low stock items" value={data?.low_stock_items ?? "—"} icon={Package} tone="text-warning" />
        {data?.revenue_today !== undefined && (
          <StatCard
            title="Revenue today"
            value={kd(data.revenue_today)}
            icon={Wallet}
            tone="text-success"
            hint={`Month to date ${kd(data.revenue_month)}`}
          />
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Today's classes</CardTitle>
          </CardHeader>
          <CardContent>
            {data?.today_classes.length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Time</TableHead>
                    <TableHead>Class</TableHead>
                    <TableHead>Instructor</TableHead>
                    <TableHead className="text-right">Booked / present</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.today_classes.map((c) => (
                    <TableRow key={c.id}>
                      <TableCell>
                        {fmtTime(c.start_time)}–{fmtTime(c.end_time)}
                      </TableCell>
                      <TableCell>{c.program}</TableCell>
                      <TableCell>{c.instructor_id ? instructorMap.get(c.instructor_id)?.full_name : "—"}</TableCell>
                      <TableCell className="text-right">
                        {c.booked}/{c.capacity} · {c.attended}
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={c.status} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <Empty>
                No classes today. Generate sessions from the timetable on the <Link href="/classes" className="underline">Classes</Link> page.
              </Empty>
            )}
          </CardContent>
        </Card>

        {isStaff && (
          <Card>
            <CardHeader>
              <CardTitle>Renewal follow-up</CardTitle>
            </CardHeader>
            <CardContent>
              {expiring.length ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Member</TableHead>
                      <TableHead>Plan</TableHead>
                      <TableHead>Ends</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {expiring.map((m) => (
                      <TableRow key={m.id}>
                        <TableCell>
                          <Link href={`/members/${m.member_id}`} className="text-brand hover:underline">
                            {m.member?.first_name} {m.member?.last_name}
                          </Link>
                          <div className="text-xs text-muted-foreground">{m.member?.phone}</div>
                        </TableCell>
                        <TableCell>{m.plan.name}</TableCell>
                        <TableCell>{fmtDate(m.end_date)}</TableCell>
                        <TableCell>
                          <StatusBadge status={m.is_expired ? "expired" : "active"} />
                          <div className="text-xs text-muted-foreground">
                            {m.is_expired ? `${-m.days_left} days ago` : `${m.days_left} days left`}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <Empty>No memberships need follow-up.</Empty>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </Page>
  );
}
