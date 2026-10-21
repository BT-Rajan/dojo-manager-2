import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Page } from "@/components/layout/page";
import { FreezeRequestsTab } from "@/components/members/freeze-requests";
import { Empty, EnumSelect, Field, Loading, StatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useApiMutation } from "@/hooks/useApiMutation";
import { useAuth } from "@/hooks/useAuth";
import { useBranch } from "@/hooks/useBranch";
import { academyNow, fmtDate, fmtDateTime, isoDate, label } from "@/lib/format";
import { api } from "@/lib/queryClient";
import type { Complaint, Incident } from "@/lib/types";
import { DateInput, TimeInput } from "@/components/common/date-inputs";

function IncidentsTab() {
  const { branchId } = useBranch();
  const { isStaff } = useAuth();
  const [open, setOpen] = useState(false);
  const [closing, setClosing] = useState<Incident | null>(null);
  const [action, setAction] = useState("");
  const [f, setF] = useState({
    occurred_date: isoDate(),
    occurred_time: academyNow(),
    type: "injury",
    persons_involved: "",
    description: "",
    action_taken: "",
    guardian_informed: "",
    witnesses: "",
  });
  const [status, setStatus] = useState("open");
  const { data: incidents = [] } = useQuery<Incident[]>({
    queryKey: ["/api/incidents", { branch_id: branchId, status: status === "all" ? undefined : status }],
    enabled: branchId !== null && isStaff,
  });
  const inv = { invalidate: ["/api/incidents", "/api/dashboard"] };
  const report = useApiMutation(
    () =>
      api("/api/incidents", {
        method: "POST",
        body: {
          ...Object.fromEntries(
            Object.entries(f)
              .filter(([k]) => !k.startsWith("occurred_"))
              .map(([k, v]) => [k, v === "" ? null : v]),
          ),
          // Academy (Kuwait) wall-clock time; the API converts it to UTC for storage.
          occurred_at: `${f.occurred_date}T${f.occurred_time}`,
          branch_id: branchId,
        },
      }),
    { ...inv, success: "Incident reported", onSuccess: () => setOpen(false) },
  );
  const update = useApiMutation(
    ({ id, body }: { id: number; body: Record<string, unknown> }) => api(`/api/incidents/${id}`, { method: "PATCH", body }),
    { ...inv, onSuccess: () => setClosing(null) },
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3 items-center">
        <Button onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4 mr-1" /> Report incident
        </Button>
        {isStaff && (
          <div className="w-36">
            <EnumSelect value={status} onChange={setStatus} options={["open", "closed", "all"]} />
          </div>
        )}
      </div>
      {!isStaff ? (
        <p className="text-sm text-muted-foreground">Incidents you report go to the branch admin and operations manager.</p>
      ) : incidents.length === 0 ? (
        <Empty>No incidents.</Empty>
      ) : (
        incidents.map((i) => (
          <Card key={i.id}>
            <CardContent className="p-4 space-y-1 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-medium">
                  <span className="font-mono text-xs mr-2">{i.ref_no}</span>
                  {label(i.type)} · {fmtDateTime(i.occurred_at)}
                </p>
                <StatusBadge status={i.status} />
              </div>
              {i.persons_involved && <p>Involved: {i.persons_involved}</p>}
              <p>{i.description}</p>
              {i.action_taken && <p className="text-muted-foreground">Action: {i.action_taken}</p>}
              {i.guardian_informed && <p className="text-muted-foreground">Guardian informed: {i.guardian_informed}</p>}
              <p className="text-xs text-muted-foreground">
                {i.reported_to_manager_at ? `Reported to manager ${fmtDateTime(i.reported_to_manager_at)}` : "Not yet reported to manager"}
              </p>
              {i.status === "open" && (
                <div className="flex gap-2 pt-2">
                  {!i.reported_to_manager_at && (
                    <Button size="sm" variant="outline" onClick={() => update.mutate({ id: i.id, body: { reported_to_manager: true } })}>
                      Reported to manager
                    </Button>
                  )}
                  <Button
                    size="sm"
                    onClick={() => {
                      setAction(i.action_taken ?? "");
                      setClosing(i);
                    }}
                  >
                    Close
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        ))
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Incident report</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Date (DD-MM-YYYY)">
              <DateInput value={f.occurred_date} onChange={(d) => setF({ ...f, occurred_date: d })} />
            </Field>
            <Field label="Time (HH:MM:SS, Kuwait)">
              <TimeInput value={f.occurred_time} onChange={(t) => setF({ ...f, occurred_time: t })} />
            </Field>
            <Field label="Type">
              <EnumSelect value={f.type} onChange={(t) => setF({ ...f, type: t })} options={["injury", "safety_hazard", "conduct", "other"]} />
            </Field>
          </div>
          <Field label="Person(s) involved (member, age, guardian)">
            <Input value={f.persons_involved} onChange={(e) => setF({ ...f, persons_involved: e.target.value })} />
          </Field>
          <Field label="What happened *">
            <Textarea rows={3} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
          </Field>
          <Field label="Action taken (first aid, ambulance, class stopped)">
            <Textarea rows={2} value={f.action_taken} onChange={(e) => setF({ ...f, action_taken: e.target.value })} />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Parent / guardian informed (who, time)">
              <Input value={f.guardian_informed} onChange={(e) => setF({ ...f, guardian_informed: e.target.value })} />
            </Field>
            <Field label="Witnesses">
              <Input value={f.witnesses} onChange={(e) => setF({ ...f, witnesses: e.target.value })} />
            </Field>
          </div>
          <Button disabled={f.description.trim().length < 3 || !f.occurred_date || !f.occurred_time || report.isPending} onClick={() => report.mutate(undefined)}>
            Submit report
          </Button>
        </DialogContent>
      </Dialog>
      <Dialog open={!!closing} onOpenChange={(o) => !o && setClosing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Close {closing?.ref_no}</DialogTitle>
          </DialogHeader>
          <Field label="Action taken">
            <Textarea rows={3} value={action} onChange={(e) => setAction(e.target.value)} />
          </Field>
          <Button
            disabled={!action.trim() || update.isPending}
            onClick={() => closing && update.mutate({ id: closing.id, body: { status: "closed", action_taken: action } })}
          >
            Close incident
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function ComplaintsTab() {
  const { branchId } = useBranch();
  const [open, setOpen] = useState(false);
  const [closing, setClosing] = useState<Complaint | null>(null);
  const [outcome, setOutcome] = useState({ text: "", informed: true, escalated: false });
  const [f, setF] = useState({ contact_name: "", contact_phone: "", channel: "desk", description: "" });
  const [status, setStatus] = useState("open");
  const { data: complaints = [], isLoading: loading_complaints } = useQuery<Complaint[]>({
    queryKey: ["/api/complaints", { branch_id: branchId, status: status === "all" ? undefined : status }],
    enabled: branchId !== null,
  });
  const inv = { invalidate: ["/api/complaints", "/api/dashboard"] };
  const log = useApiMutation(
    () =>
      api("/api/complaints", {
        method: "POST",
        body: { ...f, contact_phone: f.contact_phone || null, branch_id: branchId },
      }),
    { ...inv, success: "Complaint logged", onSuccess: () => setOpen(false) },
  );
  const close = useApiMutation(
    () =>
      api(`/api/complaints/${closing?.id}`, {
        method: "PATCH",
        body: {
          status: "closed",
          outcome: outcome.text,
          escalated: outcome.escalated,
          member_informed_on: outcome.informed ? isoDate() : null,
        },
      }),
    { ...inv, success: "Complaint closed", onSuccess: () => setClosing(null) },
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3 items-center">
        <Button onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4 mr-1" /> Log complaint
        </Button>
        <div className="w-36">
          <EnumSelect value={status} onChange={setStatus} options={["open", "closed", "all"]} />
        </div>
      </div>
      {loading_complaints ? <Loading /> : complaints.length === 0 ? (
        <Empty>No complaints.</Empty>
      ) : (
        complaints.map((c) => (
          <Card key={c.id}>
            <CardContent className="p-4 space-y-1 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-medium">
                  <span className="font-mono text-xs mr-2">{c.ref_no}</span>
                  {c.contact_name} · {label(c.channel)} · {fmtDate(c.received_on)}
                </p>
                <StatusBadge status={c.status} />
              </div>
              <p>{c.description}</p>
              {c.outcome && <p className="text-muted-foreground">Outcome: {c.outcome}</p>}
              {c.escalated && <p className="text-xs text-warning">Escalated to operations manager</p>}
              {c.status === "open" && (
                <Button
                  size="sm"
                  className="mt-2"
                  onClick={() => {
                    setOutcome({ text: "", informed: true, escalated: c.escalated });
                    setClosing(c);
                  }}
                >
                  Resolve
                </Button>
              )}
            </CardContent>
          </Card>
        ))
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Log complaint</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Member / contact *">
              <Input value={f.contact_name} onChange={(e) => setF({ ...f, contact_name: e.target.value })} />
            </Field>
            <Field label="Phone">
              <Input value={f.contact_phone} onChange={(e) => setF({ ...f, contact_phone: e.target.value })} />
            </Field>
            <Field label="Channel" className="sm:col-span-2">
              <EnumSelect
                value={f.channel}
                onChange={(c) => setF({ ...f, channel: c })}
                options={["desk", "whatsapp", "ai_agent", "call", "email", "other"]}
                labels={{ ai_agent: "AI agent" }}
              />
            </Field>
          </div>
          <Field label="Complaint *">
            <Textarea rows={3} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
          </Field>
          <Button disabled={!f.contact_name || f.description.trim().length < 3 || log.isPending} onClick={() => log.mutate(undefined)}>
            Save
          </Button>
        </DialogContent>
      </Dialog>
      <Dialog open={!!closing} onOpenChange={(o) => !o && setClosing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Resolve {closing?.ref_no}</DialogTitle>
          </DialogHeader>
          <Field label="Action / outcome">
            <Textarea rows={3} value={outcome.text} onChange={(e) => setOutcome({ ...outcome, text: e.target.value })} />
          </Field>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={outcome.informed} onCheckedChange={(c) => setOutcome({ ...outcome, informed: c === true })} />
            Member informed today
          </label>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={outcome.escalated} onCheckedChange={(c) => setOutcome({ ...outcome, escalated: c === true })} />
            Escalated to operations manager
          </label>
          <Button disabled={!outcome.text.trim() || close.isPending} onClick={() => close.mutate(undefined)}>
            Close complaint
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function Operations() {
  const { isStaff } = useAuth();
  return (
    <Page title="Operations">
      <Tabs defaultValue="incidents">
        <TabsList>
          <TabsTrigger value="incidents">Incidents</TabsTrigger>
          {isStaff && <TabsTrigger value="complaints">Complaints</TabsTrigger>}
          {isStaff && <TabsTrigger value="freezes">Freeze requests</TabsTrigger>}
        </TabsList>
        <TabsContent value="incidents">
          <IncidentsTab />
        </TabsContent>
        {isStaff && (
          <TabsContent value="complaints">
            <ComplaintsTab />
          </TabsContent>
        )}
        {isStaff && (
          <TabsContent value="freezes">
            <FreezeRequestsTab />
          </TabsContent>
        )}
      </Tabs>
    </Page>
  );
}
