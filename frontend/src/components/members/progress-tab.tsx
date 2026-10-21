import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Circle, Plus, Send, Trash2 } from "lucide-react";
import { BeltSwatch, Empty, Field, Loading, RecordSelect, StatusBadge } from "@/components/common";
import { DateInput, MonthInput } from "@/components/common/date-inputs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useApiMutation } from "@/hooks/useApiMutation";
import { useAuth } from "@/hooks/useAuth";
import { useInstructors } from "@/hooks/useLookups";
import { fmtDate, fmtDateTime, isoDate } from "@/lib/format";
import { api } from "@/lib/queryClient";
import type { Member, MemberProgress, Track } from "@/lib/types";

const TRACKS: Record<Track, string> = { kickboxing: "Kickboxing", jiujitsu: "Jiu-Jitsu", self_defence: "Self-Defence & Traditional" };

function Section({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        {action}
      </div>
      {children}
    </section>
  );
}

/** Progress to the next belt: checks, skills, evaluations, monthly notes, photo consent and rules. */
export function ProgressTab({ member }: { member: Member }) {
  const { isStaff, user } = useAuth();
  const url = `/api/members/${member.id}/progress`;
  const { data: p, isLoading } = useQuery<MemberProgress>({ queryKey: [url] });
  const { instructors, instructorMap } = useInstructors(member.branch_id);
  const isCoach = user?.role === "instructor";
  const inv = { invalidate: [url] };
  const [evalOpen, setEvalOpen] = useState(false);
  const [ev, setEv] = useState({ eval_date: isoDate(), notes: "", ready_for_test: false, instructor_id: null as number | null });
  const [noteOpen, setNoteOpen] = useState(false);
  const [note, setNote] = useState({ month: isoDate().slice(0, 7), worked_on: "", next_steps: "", instructor_id: null as number | null });
  const [consentOpen, setConsentOpen] = useState(false);
  const [consent, setConsent] = useState({ internal_records: true, social_media: false, website_marketing: false, signed_by_name: "" });

  const check = useApiMutation(
    ({ id, checked }: { id: number; checked: boolean }) => api(`/api/members/${member.id}/skills/${id}`, { method: "PUT", body: { checked } }),
    inv,
  );
  const addEval = useApiMutation(
    () => api(`/api/members/${member.id}/evaluations`, { method: "POST", body: { ...ev, notes: ev.notes || null } }),
    { ...inv, success: "Evaluation saved", onSuccess: () => setEvalOpen(false) },
  );
  const removeEval = useApiMutation((id: number) => api(`/api/evaluations/${id}`, { method: "DELETE" }), { ...inv, success: "Evaluation removed" });
  const addNote = useApiMutation(
    () => api(`/api/members/${member.id}/progress-notes`, { method: "POST", body: { ...note, month: `${note.month}-01` } }),
    { ...inv, success: "Note saved as a draft", onSuccess: () => setNoteOpen(false) },
  );
  const sendNote = useApiMutation((id: number) => api(`/api/progress-notes/${id}/send`, { method: "POST" }), {
    ...inv,
    success: "Note sent to the family",
  });
  const recordConsent = useApiMutation(() => api(`/api/members/${member.id}/consent`, { method: "POST", body: consent }), {
    invalidate: [url, `/api/members/${member.id}`],
    success: "Consent recorded",
    onSuccess: () => setConsentOpen(false),
  });

  if (isLoading || !p) return <Loading />;
  const tracks = [...new Set(p.skills.map((s) => s.track))];

  return (
    <div className="space-y-6">
      {p.belt ? (
        <Section title="Next belt">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <BeltSwatch color={p.belt.color} name={`${p.belt.name}${p.stripes ? ` · ${p.stripes} stripe(s)` : ""}`} />
            {p.next && (
              <>
                <span className="text-muted-foreground">→</span>
                <BeltSwatch color={p.next.color} name={p.next.name} />
              </>
            )}
            {p.next && (p.eligible ? <StatusBadge status="ready" /> : <StatusBadge status="not_ready" />)}
            <span className="text-xs text-muted-foreground">since {fmtDate(p.since)}</span>
          </div>
          {p.next ? (
            <ul className="grid gap-1 text-sm sm:grid-cols-2">
              {p.checks.map((c) => (
                <li key={c.code} className="flex items-center gap-2">
                  {c.ok ? <CheckCircle2 className="h-4 w-4 text-success" /> : <Circle className="h-4 w-4 text-muted-foreground" />}
                  {c.en}
                  {c.code !== "ready" && (
                    <span className="tabular text-muted-foreground">
                      {c.have}/{c.need}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">Top belt.</p>
          )}
          {p.tests.map((t) => (
            <p key={t.id} className="text-sm text-success">
              Test day: {t.title} · {fmtDate(t.event_date)}
            </p>
          ))}
        </Section>
      ) : (
        <Empty>Set the member's belt to follow their progress.</Empty>
      )}

      {p.belt && (
        <Section title={`Skills at this belt · ${p.done}/${p.total}`}>
          {p.skills.length === 0 ? (
            <p className="text-sm text-muted-foreground">No skills listed for this belt (Admin → Plans, programmes & belts).</p>
          ) : (
            <div className="grid gap-4 md:grid-cols-3">
              {tracks.map((track) => (
                <div key={track} className="space-y-1">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{TRACKS[track]}</p>
                  {p.skills
                    .filter((s) => s.track === track)
                    .map((s) => (
                      <label key={s.id} className="flex items-start gap-2 text-sm">
                        <Checkbox
                          checked={!!s.checked_on}
                          onCheckedChange={(c) => check.mutate({ id: s.id, checked: !!c })}
                          aria-label={s.name}
                          className="mt-0.5"
                        />
                        <span>
                          {s.name} <span className="text-xs text-muted-foreground">{s.category}</span>
                        </span>
                      </label>
                    ))}
                </div>
              ))}
            </div>
          )}
        </Section>
      )}

      <Section
        title="Evaluations"
        action={
          <Button size="sm" variant="outline" onClick={() => setEvalOpen(true)}>
            <Plus className="h-4 w-4 mr-1" /> Evaluation
          </Button>
        }
      >
        {p.evaluations.length === 0 ? (
          <p className="text-sm text-muted-foreground">No evaluations yet. Coaches evaluate every 4–6 weeks.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {p.evaluations.map((e) => (
              <li key={e.id} className="flex items-start justify-between gap-2 rounded border p-2">
                <div>
                  <p className="text-xs text-muted-foreground">
                    {fmtDate(e.eval_date)}
                    {e.instructor_name && ` · ${e.instructor_name}`}
                    {e.ready_for_test && (
                      <Badge variant="outline" className="ml-2 border-0 bg-success/15 text-success">
                        Ready for test
                      </Badge>
                    )}
                  </p>
                  <p>{e.notes ?? "—"}</p>
                </div>
                <Button size="icon" variant="ghost" aria-label="Remove evaluation" onClick={() => removeEval.mutate(e.id)}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section
        title="Monthly notes to the family"
        action={
          <Button size="sm" variant="outline" onClick={() => setNoteOpen(true)}>
            <Plus className="h-4 w-4 mr-1" /> Note
          </Button>
        }
      >
        {p.notes.length === 0 ? (
          <p className="text-sm text-muted-foreground">No monthly notes yet.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {p.notes.map((n) => (
              <li key={n.id} className="rounded border p-2 space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs text-muted-foreground">
                    {n.month.slice(5, 7)}-{n.month.slice(0, 4)}
                    {n.instructor_id && ` · ${instructorMap.get(n.instructor_id)?.full_name ?? ""}`}
                    {n.sent_at && ` · sent ${fmtDateTime(n.sent_at)}`}
                  </span>
                  {n.status === "draft" ? (
                    <Button size="sm" onClick={() => sendNote.mutate(n.id)} disabled={sendNote.isPending}>
                      <Send className="h-4 w-4 mr-1" /> Send to family
                    </Button>
                  ) : (
                    <StatusBadge status="sent" />
                  )}
                </div>
                <p>
                  <span className="font-medium">Worked on:</span> {n.worked_on}
                </p>
                <p>
                  <span className="font-medium">Next:</span> {n.next_steps}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section
        title="Photos and rules"
        action={
          isStaff && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setConsent({
                  internal_records: p.consent?.internal_records ?? true,
                  social_media: p.consent?.social_media ?? false,
                  website_marketing: p.consent?.website_marketing ?? false,
                  signed_by_name: member.guardian_name ?? member.full_name,
                });
                setConsentOpen(true);
              }}
            >
              Record consent
            </Button>
          )
        }
      >
        {p.consent ? (
          <div className="text-sm space-y-1">
            <p>
              Internal records: {p.consent.internal_records ? "Yes" : "No"} · Social media: {p.consent.social_media ? "Yes" : "No"} · Website and
              marketing: {p.consent.website_marketing ? "Yes" : "No"}
            </p>
            <p className="text-xs text-muted-foreground">
              Signed by {p.consent.signed_by_name} · {fmtDateTime(p.consent.signed_at)} · {p.consent.from_portal ? "member portal" : p.consent.notes ?? "front desk"}
            </p>
            {p.consent_history.length > 1 && (
              <details className="text-xs text-muted-foreground">
                <summary className="cursor-pointer">Earlier choices ({p.consent_history.length - 1})</summary>
                <ul className="mt-1 space-y-0.5">
                  {p.consent_history.slice(1).map((c) => (
                    <li key={c.id}>
                      {fmtDateTime(c.signed_at)} · internal {c.internal_records ? "yes" : "no"}, social {c.social_media ? "yes" : "no"}, website{" "}
                      {c.website_marketing ? "yes" : "no"} · {c.signed_by_name}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No photo consent recorded.</p>
        )}
        <p className="text-sm">
          {p.rules_signed ? (
            <span className="text-success">
              ✓ Academy rules ({p.rules_signed.rules_version}) signed by {p.rules_signed.signed_by_name} on {fmtDateTime(p.rules_signed.signed_at)}
              {p.rules_signed.from_portal && " in the member portal"}
            </span>
          ) : (
            <span className="text-warning">Academy rules ({p.rules_version}) not signed yet — the family can sign in the member portal.</span>
          )}
        </p>
      </Section>

      <Dialog open={evalOpen} onOpenChange={setEvalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Evaluation for {member.full_name}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Date">
              <DateInput value={ev.eval_date} onChange={(d) => setEv({ ...ev, eval_date: d })} />
            </Field>
            {!isCoach && (
              <Field label="Coach">
                <RecordSelect value={ev.instructor_id} onChange={(i) => setEv({ ...ev, instructor_id: i })} records={instructors} render={(i) => i.full_name} allowNone="—" />
              </Field>
            )}
          </div>
          <Field label="Notes for the family">
            <Textarea rows={4} value={ev.notes} maxLength={2000} onChange={(e) => setEv({ ...ev, notes: e.target.value })} />
          </Field>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={ev.ready_for_test} onCheckedChange={(c) => setEv({ ...ev, ready_for_test: !!c })} /> Ready for the next belt test
          </label>
          <Button disabled={!ev.eval_date || addEval.isPending} onClick={() => addEval.mutate(undefined)}>
            Save
          </Button>
        </DialogContent>
      </Dialog>

      <Dialog open={noteOpen} onOpenChange={setNoteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Monthly note for {member.full_name}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Month">
              <MonthInput value={note.month} onChange={(m) => setNote({ ...note, month: m })} />
            </Field>
            {!isCoach && (
              <Field label="Coach">
                <RecordSelect value={note.instructor_id} onChange={(i) => setNote({ ...note, instructor_id: i })} records={instructors} render={(i) => i.full_name} allowNone="—" />
              </Field>
            )}
          </div>
          <Field label="What they worked on">
            <Textarea rows={3} maxLength={2000} value={note.worked_on} onChange={(e) => setNote({ ...note, worked_on: e.target.value })} />
          </Field>
          <Field label="Next steps">
            <Textarea rows={3} maxLength={2000} value={note.next_steps} onChange={(e) => setNote({ ...note, next_steps: e.target.value })} />
          </Field>
          <p className="text-xs text-muted-foreground">Saved as a draft; send it when ready. The family sees it in the portal and by WhatsApp.</p>
          <Button disabled={!note.month || !note.worked_on.trim() || !note.next_steps.trim() || addNote.isPending} onClick={() => addNote.mutate(undefined)}>
            Save draft
          </Button>
        </DialogContent>
      </Dialog>

      <Dialog open={consentOpen} onOpenChange={setConsentOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Record photo consent</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">From the signed media consent form (EA-MKT-FRM-01).</p>
          {(
            [
              ["internal_records", "Internal records (progress, belt tests)"],
              ["social_media", "The academy's social media"],
              ["website_marketing", "Website and marketing"],
            ] as const
          ).map(([key, text]) => (
            <label key={key} className="flex items-center gap-2 text-sm">
              <Checkbox checked={consent[key]} onCheckedChange={(c) => setConsent({ ...consent, [key]: !!c })} /> {text}
            </label>
          ))}
          <Field label="Signed by">
            <Input value={consent.signed_by_name} onChange={(e) => setConsent({ ...consent, signed_by_name: e.target.value })} />
          </Field>
          <Button disabled={!consent.signed_by_name.trim() || recordConsent.isPending} onClick={() => recordConsent.mutate(undefined)}>
            Save
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}
