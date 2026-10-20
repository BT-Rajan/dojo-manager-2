import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { addDays, startOfWeek, subDays } from "date-fns";
import { ChevronLeft, ChevronRight, Printer } from "lucide-react";
import { Page } from "@/components/layout/page";
import { Empty } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useBranch } from "@/hooks/useBranch";
import { academyToday, fmtDateTime, fmtDay, isoDate, kd, label } from "@/lib/format";
import { DateInput } from "@/components/common/date-inputs";

interface WeeklySales {
  week_start: string;
  week_end: string;
  total: string;
  by_method: Record<string, string>;
  by_category: Record<string, string>;
  transactions: { payment_id: number; paid_at: string; member: string | null; category: string; method: string; amount: string }[];
}
interface WeeklyBranch {
  measures: { measure: string; this_week: number; last_week: number; change: number }[];
}
interface AttendanceRow {
  program_id: number;
  program: string;
  classes: number;
  attendances: number;
  average_class_size: number;
}

export default function Reports() {
  const { branchId, branch } = useBranch();
  const [weekStart, setWeekStart] = useState(() => startOfWeek(academyToday(), { weekStartsOn: 6 }));
  const [range, setRange] = useState({ from: isoDate(subDays(academyToday(), 30)), to: isoDate() });
  const ws = isoDate(weekStart);
  const enabled = branchId !== null;
  const { data: sales } = useQuery<WeeklySales>({
    queryKey: ["/api/reports/weekly-sales", { branch_id: branchId, week_start: ws }],
    enabled,
  });
  const { data: weekly } = useQuery<WeeklyBranch>({
    queryKey: ["/api/reports/weekly-branch", { branch_id: branchId, week_start: ws }],
    enabled,
  });
  const { data: attendance = [] } = useQuery<AttendanceRow[]>({
    queryKey: ["/api/reports/attendance", { branch_id: branchId, date_from: range.from, date_to: range.to }],
    enabled,
  });
  const maxAtt = Math.max(1, ...attendance.map((a) => a.attendances));

  return (
    <Page
      title="Reports"
      actions={
        <Button variant="outline" onClick={() => window.print()}>
          <Printer className="h-4 w-4 mr-1" /> Print
        </Button>
      }
    >
      <div className="flex items-center gap-2">
        <Button variant="outline" size="icon" onClick={() => setWeekStart(addDays(weekStart, -7))} aria-label="Previous week">
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="font-medium">
          Week {fmtDay(isoDate(weekStart))} – {fmtDay(isoDate(addDays(weekStart, 6)))} · {branch?.name}
        </span>
        <Button variant="outline" size="icon" onClick={() => setWeekStart(addDays(weekStart, 7))} aria-label="Next week">
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Weekly branch report</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Measure</TableHead>
                  <TableHead className="text-right">This week</TableHead>
                  <TableHead className="text-right">Last week</TableHead>
                  <TableHead className="text-right">Change</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {weekly?.measures.map((m) => (
                  <TableRow key={m.measure}>
                    <TableCell>{label(m.measure)}</TableCell>
                    <TableCell className="text-right">{m.this_week}</TableCell>
                    <TableCell className="text-right">{m.last_week}</TableCell>
                    <TableCell className={`text-right ${m.change > 0 ? "text-success" : m.change < 0 ? "text-destructive" : ""}`}>
                      {m.change > 0 ? `+${m.change}` : m.change}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Weekly sales · {sales ? kd(sales.total) : ""}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {sales && (
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="font-medium mb-1">By method</p>
                  {Object.entries(sales.by_method).map(([k, v]) => (
                    <p key={k} className="flex justify-between">
                      <span>{k === "knet" ? "KNET" : label(k)}</span>
                      <span>{kd(v)}</span>
                    </p>
                  ))}
                </div>
                <div>
                  <p className="font-medium mb-1">By category</p>
                  {Object.entries(sales.by_category).map(([k, v]) => (
                    <p key={k} className="flex justify-between">
                      <span>{label(k)}</span>
                      <span>{kd(v)}</span>
                    </p>
                  ))}
                </div>
              </div>
            )}
            {!sales?.transactions.length ? (
              <Empty>No sales this week.</Empty>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead>
                    <TableHead>Member</TableHead>
                    <TableHead>Category</TableHead>
                    <TableHead>Method</TableHead>
                    <TableHead className="text-right">Amount</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sales.transactions.map((t) => (
                    <TableRow key={t.payment_id}>
                      <TableCell>{fmtDateTime(t.paid_at)}</TableCell>
                      <TableCell>{t.member ?? "—"}</TableCell>
                      <TableCell>{label(t.category)}</TableCell>
                      <TableCell>{t.method === "knet" ? "KNET" : label(t.method)}</TableCell>
                      <TableCell className="text-right">{kd(t.amount)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
          <CardTitle>Attendance by programme</CardTitle>
          <div className="flex gap-2 items-center text-sm">
            <DateInput value={range.from} onChange={(from) => from && setRange({ ...range, from })} aria-label="From" />
            <span>to</span>
            <DateInput value={range.to} onChange={(to) => to && setRange({ ...range, to })} aria-label="To" />
          </div>
        </CardHeader>
        <CardContent>
          {attendance.length === 0 ? (
            <Empty>No classes in this period.</Empty>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Programme</TableHead>
                  <TableHead className="text-right">Classes</TableHead>
                  <TableHead className="text-right">Attendances</TableHead>
                  <TableHead className="text-right">Avg. class size</TableHead>
                  <TableHead className="w-1/3" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {attendance.map((a) => (
                  <TableRow key={a.program_id}>
                    <TableCell>{a.program}</TableCell>
                    <TableCell className="text-right">{a.classes}</TableCell>
                    <TableCell className="text-right">{a.attendances}</TableCell>
                    <TableCell className="text-right">{a.average_class_size}</TableCell>
                    <TableCell>
                      <div className="h-2 rounded bg-muted" aria-hidden>
                        <div className="h-2 rounded bg-brand" style={{ width: `${(a.attendances / maxAtt) * 100}%` }} />
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </Page>
  );
}
