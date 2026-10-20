import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation } from "wouter";
import { addDays } from "date-fns";
import { Plus } from "lucide-react";
import { Page } from "@/components/layout/page";
import { Empty, EnumSelect, Field, RecordSelect, StatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { useApiMutation } from "@/hooks/useApiMutation";
import { useBranch } from "@/hooks/useBranch";
import { usePrograms } from "@/hooks/useLookups";
import { academyToday, fmtDate, fmtTime, isoDate, label } from "@/lib/format";
import { api } from "@/lib/queryClient";
import type { ClassSession, Lead, Member } from "@/lib/types";

const SOURCES = ["walk_in", "whatsapp", "ai_agent", "website", "phone", "referral", "social", "other"];
const OPEN_STATUSES = ["new", "contacted", "trial_booked", "trial_attended"];

type Action = { kind: "trial" | "convert" | "lost" | "status"; lead: Lead } | null;

export default function Leads() {
  const { branchId } = useBranch();
  const { programs, programMap } = usePrograms();
  const [, setLocation] = useLocation();
  const [filter, setFilter] = useState("open");
  const [open, setOpen] = useState(false);
  const [action, setAction] = useState<Action>(null);
  const [form, setForm] = useState({ full_name: "", phone: "", source: "whatsapp", age: "", next_action: "", notes: "" });
  const [programId, setProgramId] = useState<number | null>(null);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [names, setNames] = useState({ first_name: "", last_name: "" });
  const [reason, setReason] = useState("");

  const params =
    filter === "open" ? { open_only: true } : filter === "all" ? {} : { status: filter };
  const { data: leads = [] } = useQuery<Lead[]>({
    queryKey: ["/api/leads", { branch_id: branchId, ...params }],
    enabled: branchId !== null,
  });
  const { data: upcoming = [] } = useQuery<ClassSession[]>({
    queryKey: ["/api/sessions", { branch_id: branchId, date_from: isoDate(), date_to: isoDate(addDays(academyToday(), 14)) }],
    enabled: action?.kind === "trial",
  });

  const done = () => setAction(null);
  const inv = { invalidate: ["/api/leads", "/api/dashboard"] };
  const create = useApiMutation(
    () =>
      api("/api/leads", {
        method: "POST",
        body: {
          branch_id: branchId,
          full_name: form.full_name,
          phone: form.phone,
          source: form.source,
          age: form.age ? Number(form.age) : null,
          program_id: programId,
          next_action: form.next_action || null,
          notes: form.notes || null,
        },
      }),
    { ...inv, success: "Lead recorded", onSuccess: () => setOpen(false) },
  );
  const patch = useApiMutation(
    ({ id, body }: { id: number; body: Record<string, unknown> }) => api(`/api/leads/${id}`, { method: "PATCH", body }),
    { ...inv, onSuccess: done },
  );
  const bookTrial = useApiMutation(
    () => api(`/api/leads/${action?.lead.id}/book-trial`, { method: "POST", body: { session_id: sessionId } }),
    { ...inv, success: "Trial booked", onSuccess: done },
  );
  const convert = useApiMutation(
    () => api<Member>(`/api/leads/${action?.lead.id}/convert`, { method: "POST", body: names }),
    {
      invalidate: [...inv.invalidate, "/api/members"],
      success: "Registered as member — add their membership next",
      onSuccess: (m) => setLocation(`/members/${m.id}`),
    },
  );

  const startConvert = (lead: Lead) => {
    const [first, ...rest] = lead.full_name.split(" ");
    setNames({ first_name: first, last_name: rest.join(" ") });
    setAction({ kind: "convert", lead });
  };

  return (
    <Page
      title="Leads & trials"
      actions={
        <Button onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4 mr-1" /> New enquiry
        </Button>
      }
    >
      <Card>
        <CardContent className="p-4 space-y-4">
          <div className="w-52">
            <EnumSelect value={filter} onChange={setFilter} options={["open", ...OPEN_STATUSES, "converted", "lost", "all"]} />
          </div>
          {leads.length === 0 ? (
            <Empty>No leads.</Empty>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Interest</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Next action</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {leads.map((l) => {
                  const isOpen = OPEN_STATUSES.includes(l.status);
                  return (
                    <TableRow key={l.id}>
                      <TableCell>
                        {l.full_name}
                        <div className="text-xs text-muted-foreground">{l.phone}</div>
                      </TableCell>
                      <TableCell>{label(l.source)}</TableCell>
                      <TableCell>{l.program_id ? programMap.get(l.program_id)?.name : "—"}</TableCell>
                      <TableCell>
                        <StatusBadge status={l.status} />
                      </TableCell>
                      <TableCell>
                        {l.next_action ?? "—"}
                        {l.next_action_date && <div className="text-xs text-muted-foreground">{fmtDate(l.next_action_date)}</div>}
                      </TableCell>
                      <TableCell className="text-right space-x-1 whitespace-nowrap">
                        {isOpen && (
                          <>
                            {l.status === "new" && (
                              <Button size="sm" variant="ghost" onClick={() => patch.mutate({ id: l.id, body: { status: "contacted" } })}>
                                Contacted
                              </Button>
                            )}
                            {l.status === "trial_booked" && (
                              <Button size="sm" variant="ghost" onClick={() => patch.mutate({ id: l.id, body: { status: "trial_attended" } })}>
                                Attended
                              </Button>
                            )}
                            <Button size="sm" variant="outline" onClick={() => setAction({ kind: "trial", lead: l })}>
                              Book trial
                            </Button>
                            <Button size="sm" onClick={() => startConvert(l)}>
                              Sign up
                            </Button>
                            <Button size="sm" variant="ghost" className="text-destructive" onClick={() => setAction({ kind: "lost", lead: l })}>
                              Lost
                            </Button>
                          </>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New enquiry</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Name *">
              <Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
            </Field>
            <Field label="Phone *">
              <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            </Field>
            <Field label="Source">
              <EnumSelect value={form.source} onChange={(s) => setForm({ ...form, source: s })} options={SOURCES} labels={{ ai_agent: "AI agent" }} />
            </Field>
            <Field label="Age">
              <Input type="number" min={2} value={form.age} onChange={(e) => setForm({ ...form, age: e.target.value })} />
            </Field>
            <Field label="Interested in" className="sm:col-span-2">
              <RecordSelect value={programId} onChange={setProgramId} records={programs} render={(p) => p.name} allowNone="Not sure yet" />
            </Field>
            <Field label="Next action" className="sm:col-span-2">
              <Input value={form.next_action} onChange={(e) => setForm({ ...form, next_action: e.target.value })} />
            </Field>
            <Field label="Notes" className="sm:col-span-2">
              <Textarea rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </Field>
          </div>
          <Button disabled={!form.full_name || !form.phone || create.isPending} onClick={() => create.mutate(undefined)}>
            Save
          </Button>
        </DialogContent>
      </Dialog>

      <Dialog open={!!action} onOpenChange={(o) => !o && done()}>
        <DialogContent>
          {action?.kind === "trial" && (
            <>
              <DialogHeader>
                <DialogTitle>Book trial for {action.lead.full_name}</DialogTitle>
              </DialogHeader>
              <Field label="Class (next 14 days)">
                <RecordSelect
                  value={sessionId}
                  onChange={setSessionId}
                  records={upcoming.filter((s) => s.status === "scheduled")}
                  render={(s) => `${fmtDate(s.session_date)} ${fmtTime(s.start_time)} — ${programMap.get(s.program_id)?.name ?? ""}`}
                />
              </Field>
              <Button disabled={!sessionId || bookTrial.isPending} onClick={() => bookTrial.mutate(undefined)}>
                Book trial
              </Button>
            </>
          )}
          {action?.kind === "convert" && (
            <>
              <DialogHeader>
                <DialogTitle>Register {action.lead.full_name} as a member</DialogTitle>
              </DialogHeader>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="First name">
                  <Input value={names.first_name} onChange={(e) => setNames({ ...names, first_name: e.target.value })} />
                </Field>
                <Field label="Last name">
                  <Input value={names.last_name} onChange={(e) => setNames({ ...names, last_name: e.target.value })} />
                </Field>
              </div>
              <Button disabled={!names.first_name || !names.last_name || convert.isPending} onClick={() => convert.mutate(undefined)}>
                Register
              </Button>
            </>
          )}
          {action?.kind === "lost" && (
            <>
              <DialogHeader>
                <DialogTitle>Mark {action.lead.full_name} as lost</DialogTitle>
              </DialogHeader>
              <Field label="Reason">
                <Input value={reason} onChange={(e) => setReason(e.target.value)} />
              </Field>
              <Button
                variant="destructive"
                disabled={!reason || patch.isPending}
                onClick={() => patch.mutate({ id: action.lead.id, body: { status: "lost", lost_reason: reason } })}
              >
                Mark lost
              </Button>
            </>
          )}
        </DialogContent>
      </Dialog>
    </Page>
  );
}
