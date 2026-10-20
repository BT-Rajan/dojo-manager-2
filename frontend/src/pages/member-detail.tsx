import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRoute } from "wouter";
import { Pencil, Phone, Plus } from "lucide-react";
import { Page } from "@/components/layout/page";
import { BeltSwatch, Empty, EnumSelect, Field, RecordSelect, StatusBadge } from "@/components/common";
import { MemberForm, toPayload } from "@/components/common/member-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApiMutation } from "@/hooks/useApiMutation";
import { useAuth } from "@/hooks/useAuth";
import { usePlans, usePrograms } from "@/hooks/useLookups";
import { fmtDate, fmtDateTime, fmtTime, kd, label } from "@/lib/format";
import { api } from "@/lib/queryClient";
import type { FollowUp, Member, Membership, Payment } from "@/lib/types";

const METHODS = ["knet", "card", "cash"] as const;
const METHOD_LABELS = { knet: "KNET", card: "Visa / Mastercard", cash: "Cash" };

export default function MemberDetail() {
  const [, params] = useRoute("/members/:id");
  const id = Number(params?.id);
  const { isStaff } = useAuth();
  const { programMap } = usePrograms();
  const { data: member } = useQuery<Member>({ queryKey: [`/api/members/${id}`] });
  const { plans } = usePlans(member?.branch_id ?? null);
  const { data: memberships = [] } = useQuery<Membership[]>({ queryKey: [`/api/members/${id}/memberships`] });
  const { data: payments = [] } = useQuery<Payment[]>({
    queryKey: ["/api/payments", { member_id: id }],
    enabled: isStaff,
  });
  const { data: attendance = [] } = useQuery<
    { session_id: number; session_date: string; start_time: string; program_id: number; status: string }[]
  >({ queryKey: [`/api/members/${id}/attendance`] });
  const { data: followups = [] } = useQuery<FollowUp[]>({
    queryKey: ["/api/followups", { member_id: id }],
    enabled: isStaff,
  });

  const [editing, setEditing] = useState(false);
  const [adding, setAdding] = useState(false);
  const [logging, setLogging] = useState(false);
  const [planId, setPlanId] = useState<number | null>(null);
  const [startDate, setStartDate] = useState("");
  const [method, setMethod] = useState<string>("knet");
  const [fu, setFu] = useState({ method: "whatsapp", outcome: "will_renew", next_action: "" });

  const update = useApiMutation(
    (body: Record<string, unknown>) => api<Member>(`/api/members/${id}`, { method: "PATCH", body }),
    { invalidate: ["/api/members"], success: "Member updated", onSuccess: () => setEditing(false) },
  );
  const addMembership = useApiMutation(
    () =>
      api("/api/memberships", {
        method: "POST",
        body: {
          member_id: id,
          plan_id: planId,
          start_date: startDate || null,
          payment: method === "unpaid" ? null : { method },
        },
      }),
    {
      invalidate: [`/api/members/${id}`, "/api/payments", "/api/dashboard", "/api/memberships"],
      success: "Membership added",
      onSuccess: () => setAdding(false),
    },
  );
  const logFollowUp = useApiMutation(
    () =>
      api("/api/followups", {
        method: "POST",
        body: { member_id: id, ...fu, next_action: fu.next_action || null, membership_id: memberships[0]?.id ?? null },
      }),
    { invalidate: ["/api/followups"], success: "Follow-up logged", onSuccess: () => setLogging(false) },
  );

  if (!member) return <Page title="Member" needsBranch={false}>{null}</Page>;
  const current = memberships.find((m) => m.status === "active" && !m.is_expired && m.days_left >= 0);

  return (
    <Page
      title={member.full_name}
      subtitle={`${member.member_no} · joined ${fmtDate(member.joined_on)}`}
      needsBranch={false}
      actions={
        isStaff && (
          <>
            <Button variant="outline" onClick={() => setEditing(true)}>
              <Pencil className="h-4 w-4 mr-1" /> Edit
            </Button>
            <Button onClick={() => setAdding(true)}>
              <Plus className="h-4 w-4 mr-1" /> {current ? "Renew" : "Add membership"}
            </Button>
          </>
        )
      }
    >
      <div className="grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Profile</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex items-center gap-2">
              <StatusBadge status={member.status} />
              {member.belt_rank && (
                <BeltSwatch
                  color={member.belt_rank.color}
                  name={`${member.belt_rank.name} belt${member.stripes ? ` · ${member.stripes} stripe(s)` : ""}`}
                />
              )}
            </div>
            <p className="flex items-center gap-1">
              <Phone className="h-3 w-3" /> {member.phone}
            </p>
            {member.email && <p>{member.email}</p>}
            <p>Age: {member.age ?? "—"}</p>
            {member.guardian_name && (
              <p>
                Guardian: {member.guardian_name} {member.guardian_phone && `(${member.guardian_phone})`}
              </p>
            )}
            {member.emergency_contact_name && (
              <p>
                Emergency: {member.emergency_contact_name} {member.emergency_contact_phone}
              </p>
            )}
            {member.health_notes && (
              <p className="rounded bg-amber-50 p-2 text-amber-900">Health notes: {member.health_notes}</p>
            )}
            <p>Media consent: {member.media_consent ? "Yes" : "No"}</p>
            {member.notes && <p className="text-gray-600">{member.notes}</p>}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardContent className="pt-6">
            <Tabs defaultValue="memberships">
              <TabsList>
                <TabsTrigger value="memberships">Memberships</TabsTrigger>
                {isStaff && <TabsTrigger value="payments">Payments</TabsTrigger>}
                <TabsTrigger value="attendance">Attendance</TabsTrigger>
                {isStaff && <TabsTrigger value="followups">Follow-ups</TabsTrigger>}
              </TabsList>

              <TabsContent value="memberships">
                {memberships.length === 0 ? (
                  <Empty>No memberships yet.</Empty>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Plan</TableHead>
                        <TableHead>From</TableHead>
                        <TableHead>To</TableHead>
                        <TableHead>Price</TableHead>
                        <TableHead>Status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {memberships.map((m) => (
                        <TableRow key={m.id}>
                          <TableCell>{m.plan.name}</TableCell>
                          <TableCell>{fmtDate(m.start_date)}</TableCell>
                          <TableCell>{fmtDate(m.end_date)}</TableCell>
                          <TableCell>{kd(m.price)}</TableCell>
                          <TableCell>
                            <StatusBadge status={m.status === "active" && m.is_expired ? "expired" : m.status} />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </TabsContent>

              <TabsContent value="payments">
                {payments.length === 0 ? (
                  <Empty>No payments.</Empty>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Date</TableHead>
                        <TableHead>Category</TableHead>
                        <TableHead>Method</TableHead>
                        <TableHead className="text-right">Amount</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {payments.map((p) => (
                        <TableRow key={p.id}>
                          <TableCell>{fmtDateTime(p.paid_at)}</TableCell>
                          <TableCell>{label(p.category)}</TableCell>
                          <TableCell>{METHOD_LABELS[p.method]}</TableCell>
                          <TableCell className="text-right">{kd(p.amount)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </TabsContent>

              <TabsContent value="attendance">
                {attendance.length === 0 ? (
                  <Empty>No classes attended yet.</Empty>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Date</TableHead>
                        <TableHead>Time</TableHead>
                        <TableHead>Class</TableHead>
                        <TableHead>Status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {attendance.map((a) => (
                        <TableRow key={a.session_id}>
                          <TableCell>{fmtDate(a.session_date)}</TableCell>
                          <TableCell>{fmtTime(a.start_time)}</TableCell>
                          <TableCell>{programMap.get(a.program_id)?.name}</TableCell>
                          <TableCell>
                            <StatusBadge status={a.status} />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </TabsContent>

              <TabsContent value="followups" className="space-y-3">
                <Button size="sm" variant="outline" onClick={() => setLogging(true)}>
                  <Plus className="h-4 w-4 mr-1" /> Log contact
                </Button>
                {followups.length === 0 ? (
                  <Empty>No renewal contacts logged.</Empty>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>When</TableHead>
                        <TableHead>Method</TableHead>
                        <TableHead>Outcome</TableHead>
                        <TableHead>Next action</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {followups.map((f) => (
                        <TableRow key={f.id}>
                          <TableCell>{fmtDateTime(f.contacted_at)}</TableCell>
                          <TableCell>{label(f.method)}</TableCell>
                          <TableCell>{label(f.outcome)}</TableCell>
                          <TableCell>{f.next_action ?? "—"}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </div>

      <Dialog open={editing} onOpenChange={setEditing}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Edit member</DialogTitle>
          </DialogHeader>
          <MemberForm initial={member} submitLabel="Save" busy={update.isPending} onSubmit={(v) => update.mutate(toPayload(v))} />
        </DialogContent>
      </Dialog>

      <Dialog open={adding} onOpenChange={setAdding}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{current ? "Renew membership" : "Add membership"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <Field label="Plan">
              <RecordSelect
                value={planId}
                onChange={setPlanId}
                records={plans}
                render={(p) => `${p.name} — ${kd(p.price)} / ${p.duration_days} days`}
              />
            </Field>
            <Field label="Start date (blank = today, or day after current membership ends)">
              <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </Field>
            <Field label="Payment">
              <EnumSelect
                value={method}
                onChange={setMethod}
                options={[...METHODS, "unpaid"]}
                labels={{ ...METHOD_LABELS, unpaid: "Not paid yet" }}
              />
            </Field>
            <Button className="w-full" disabled={!planId || addMembership.isPending} onClick={() => addMembership.mutate(undefined)}>
              Save
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={logging} onOpenChange={setLogging}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Log renewal contact</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <Field label="Contact method">
              <EnumSelect
                value={fu.method}
                onChange={(m) => setFu({ ...fu, method: m })}
                options={["whatsapp", "call", "sms", "email", "in_person"]}
              />
            </Field>
            <Field label="Outcome">
              <EnumSelect
                value={fu.outcome}
                onChange={(o) => setFu({ ...fu, outcome: o })}
                options={["renewed", "will_renew", "not_renewing", "no_answer", "other"]}
              />
            </Field>
            <Field label="Next action">
              <Input value={fu.next_action} onChange={(e) => setFu({ ...fu, next_action: e.target.value })} />
            </Field>
            <Button className="w-full" disabled={logFollowUp.isPending} onClick={() => logFollowUp.mutate(undefined)}>
              Save
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </Page>
  );
}
