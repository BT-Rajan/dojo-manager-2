import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { BeltSwatch, EnumSelect, Field } from "@/components/common";
import { Button } from "@/components/ui/button";
import { DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useApiMutation } from "@/hooks/useApiMutation";
import { api } from "@/lib/queryClient";
import type { Belt, BeltSkill, Track } from "@/lib/types";

const TRACKS: Record<Track, string> = { kickboxing: "Kickboxing", jiujitsu: "Jiu-Jitsu", self_defence: "Self-Defence & Traditional" };

/** One belt's test requirements, Arabic names and skills (what families see in the portal). */
export function BeltCurriculumDialog({ belt, onClose }: { belt: Belt; onClose: () => void }) {
  const url = `/api/belts/${belt.id}/skills`;
  const { data: skills = [] } = useQuery<BeltSkill[]>({ queryKey: [url, { include_inactive: true }] });
  const [f, setF] = useState({
    name_ar: belt.name_ar ?? "",
    bjj_stripe_ar: belt.bjj_stripe_ar ?? "",
    seminars_required: String(belt.seminars_required),
    min_classes: String(belt.min_classes),
    min_weeks: String(belt.min_weeks),
    min_evaluations: String(belt.min_evaluations),
  });
  const [skill, setSkill] = useState({ track: "kickboxing", category: "", name: "" });
  const save = useApiMutation(
    () =>
      api(`/api/belts/${belt.id}`, {
        method: "PATCH",
        body: {
          name_ar: f.name_ar || null,
          bjj_stripe_ar: f.bjj_stripe_ar || null,
          seminars_required: Number(f.seminars_required),
          min_classes: Number(f.min_classes),
          min_weeks: Number(f.min_weeks),
          min_evaluations: Number(f.min_evaluations),
        },
      }),
    { invalidate: ["/api/belts", "/api/members"], success: "Belt saved", onSuccess: onClose },
  );
  const add = useApiMutation(() => api(url, { method: "POST", body: skill }), {
    invalidate: [url],
    success: "Skill added",
    onSuccess: () => setSkill({ ...skill, name: "" }),
  });
  const toggle = useApiMutation((s: BeltSkill) => api(`/api/skills/${s.id}`, { method: "PATCH", body: { is_active: !s.is_active } }), {
    invalidate: [url],
  });
  const num = (k: keyof typeof f) => <Input type="number" min={0} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />;

  return (
    <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
      <DialogHeader>
        <DialogTitle>
          <BeltSwatch color={belt.color} name={`${belt.name} belt`} />
        </DialogTitle>
      </DialogHeader>
      <p className="text-sm text-muted-foreground">Needed since the last belt before testing for this one.</p>
      <div className="grid gap-3 grid-cols-2 sm:grid-cols-4">
        <Field label="Classes">{num("min_classes")}</Field>
        <Field label="Weeks">{num("min_weeks")}</Field>
        <Field label="Seminars (total)">{num("seminars_required")}</Field>
        <Field label="Evaluations">{num("min_evaluations")}</Field>
        <Field label="Arabic name" className="col-span-2">
          <Input dir="rtl" value={f.name_ar} onChange={(e) => setF({ ...f, name_ar: e.target.value })} />
        </Field>
        <Field label="Arabic stripe" className="col-span-2">
          <Input dir="rtl" value={f.bjj_stripe_ar} onChange={(e) => setF({ ...f, bjj_stripe_ar: e.target.value })} />
        </Field>
      </div>
      <Button className="justify-self-start" disabled={save.isPending} onClick={() => save.mutate(undefined)}>
        Save belt
      </Button>
      <div className="border-t pt-4 space-y-3">
        <h3 className="font-semibold">Skills ({skills.filter((s) => s.is_active).length})</h3>
        <div className="grid gap-4 md:grid-cols-3">
          {(Object.keys(TRACKS) as Track[]).map((track) => (
            <div key={track} className="space-y-1 text-sm">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{TRACKS[track]}</p>
              {skills
                .filter((s) => s.track === track)
                .map((s) => (
                  <label key={s.id} className={`flex items-center justify-between gap-2 ${s.is_active ? "" : "opacity-50"}`}>
                    <span>
                      {s.name} <span className="text-xs text-muted-foreground">{s.category}</span>
                    </span>
                    <Switch checked={s.is_active} onCheckedChange={() => toggle.mutate(s)} aria-label={`${s.name} in use`} />
                  </label>
                ))}
            </div>
          ))}
        </div>
        <div className="grid gap-2 sm:grid-cols-[1fr_1fr_2fr_auto] items-end">
          <Field label="Track">
            <EnumSelect value={skill.track} onChange={(t) => setSkill({ ...skill, track: t })} options={Object.keys(TRACKS)} labels={TRACKS} />
          </Field>
          <Field label="Category">
            <Input placeholder="Strikes, Kicks…" value={skill.category} onChange={(e) => setSkill({ ...skill, category: e.target.value })} />
          </Field>
          <Field label="Skill">
            <Input value={skill.name} onChange={(e) => setSkill({ ...skill, name: e.target.value })} />
          </Field>
          <Button disabled={!skill.category || !skill.name || add.isPending} onClick={() => add.mutate(undefined)}>
            <Plus className="h-4 w-4 mr-1" /> Add
          </Button>
        </div>
      </div>
    </DialogContent>
  );
}
