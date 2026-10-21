import { useState, type FormEvent } from "react";
import { Field, EnumSelect, RecordSelect } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useBelts } from "@/hooks/useLookups";
import type { Member } from "@/lib/types";
import { DateInput } from "@/components/common/date-inputs";

export type MemberFormValues = {
  first_name: string;
  last_name: string;
  first_name_ar: string;
  last_name_ar: string;
  phone: string;
  email: string;
  date_of_birth: string;
  gender: string;
  civil_id: string;
  guardian_name: string;
  guardian_phone: string;
  emergency_contact_name: string;
  emergency_contact_phone: string;
  health_notes: string;
  media_consent: boolean;
  belt_rank_id: number | null;
  notes: string;
};

const blank: MemberFormValues = {
  first_name: "",
  last_name: "",
  first_name_ar: "",
  last_name_ar: "",
  phone: "",
  email: "",
  date_of_birth: "",
  gender: "",
  civil_id: "",
  guardian_name: "",
  guardian_phone: "",
  emergency_contact_name: "",
  emergency_contact_phone: "",
  health_notes: "",
  media_consent: false,
  belt_rank_id: null,
  notes: "",
};

/** Empty strings become null so optional fields are cleared rather than sent as "". */
export function toPayload(v: MemberFormValues) {
  const out: Record<string, unknown> = {};
  for (const [k, val] of Object.entries(v)) out[k] = val === "" ? null : val;
  return out;
}

/** Registration form (covers the front-desk registration sheet). */
export function MemberForm({
  initial,
  submitLabel,
  busy,
  onSubmit,
}: {
  initial?: Member;
  submitLabel: string;
  busy?: boolean;
  onSubmit: (values: MemberFormValues) => void;
}) {
  const { belts } = useBelts();
  const [v, setV] = useState<MemberFormValues>(() =>
    initial
      ? (Object.fromEntries(
          Object.keys(blank).map((k) => [k, (initial as unknown as Record<string, unknown>)[k] ?? (blank as Record<string, unknown>)[k]]),
        ) as MemberFormValues)
      : blank,
  );
  const set = <K extends keyof MemberFormValues>(k: K, val: MemberFormValues[K]) => setV((s) => ({ ...s, [k]: val }));
  const text = (k: keyof MemberFormValues) => ({
    value: v[k] as string,
    onChange: (e: { target: { value: string } }) => set(k, e.target.value as never),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit(v);
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="First name *">
          <Input required {...text("first_name")} />
        </Field>
        <Field label="Last name *">
          <Input required {...text("last_name")} />
        </Field>
        <Field label="First name (Arabic)">
          <Input dir="rtl" {...text("first_name_ar")} />
        </Field>
        <Field label="Last name (Arabic)">
          <Input dir="rtl" {...text("last_name_ar")} />
        </Field>
        <Field label="Mobile / WhatsApp *">
          <Input required inputMode="tel" {...text("phone")} />
        </Field>
        <Field label="Email">
          <Input type="email" {...text("email")} />
        </Field>
        <Field label="Date of birth">
          <DateInput value={v.date_of_birth} onChange={(d) => set("date_of_birth", d)} />
        </Field>
        <Field label="Gender">
          <EnumSelect value={v.gender || undefined} onChange={(g) => set("gender", g)} options={["male", "female"]} />
        </Field>
        <Field label="Civil ID (12 digits)">
          <Input inputMode="numeric" maxLength={12} {...text("civil_id")} />
        </Field>
        <Field label="Belt">
          <RecordSelect
            value={v.belt_rank_id}
            onChange={(id) => set("belt_rank_id", id)}
            records={belts}
            render={(b) => b.name}
            allowNone="No belt yet"
          />
        </Field>
        <Field label="Parent / guardian (under 18)">
          <Input {...text("guardian_name")} />
        </Field>
        <Field label="Guardian phone">
          <Input inputMode="tel" {...text("guardian_phone")} />
        </Field>
        <Field label="Emergency contact">
          <Input {...text("emergency_contact_name")} />
        </Field>
        <Field label="Emergency phone">
          <Input inputMode="tel" {...text("emergency_contact_phone")} />
        </Field>
      </div>
      <Field label="Health conditions / injuries / allergies">
        <Textarea rows={2} {...text("health_notes")} />
      </Field>
      <Field label="Notes">
        <Textarea rows={2} {...text("notes")} />
      </Field>
      <label className="flex items-center gap-2 text-sm">
        <Checkbox checked={v.media_consent} onCheckedChange={(c) => set("media_consent", c === true)} />
        Photo / video media consent given
      </label>
      <Button type="submit" disabled={busy} className="w-full">
        {submitLabel}
      </Button>
    </form>
  );
}
