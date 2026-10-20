import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { label as labelize } from "@/lib/format";
import { cn } from "@/lib/utils";

export function StatCard({
  title,
  value,
  icon: Icon,
  tone = "text-brand",
  hint,
}: {
  title: string;
  value: ReactNode;
  icon: LucideIcon;
  tone?: string;
  hint?: string;
}) {
  return (
    <Card className="card-hover">
      <CardContent className="p-5 flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-500">{title}</p>
          <p className="text-2xl font-bold text-gray-900">{value}</p>
          {hint && <p className="text-xs text-gray-400 mt-1">{hint}</p>}
        </div>
        <Icon className={cn("h-8 w-8", tone)} />
      </CardContent>
    </Card>
  );
}

const TONES: Record<string, string> = {
  active: "bg-green-100 text-green-800",
  approved: "bg-green-100 text-green-800",
  received: "bg-green-100 text-green-800",
  present: "bg-green-100 text-green-800",
  pass: "bg-green-100 text-green-800",
  converted: "bg-green-100 text-green-800",
  completed: "bg-green-100 text-green-800",
  closed: "bg-gray-100 text-gray-700",
  scheduled: "bg-blue-100 text-blue-800",
  booked: "bg-blue-100 text-blue-800",
  planned: "bg-blue-100 text-blue-800",
  submitted: "bg-blue-100 text-blue-800",
  in_transit: "bg-blue-100 text-blue-800",
  trial_booked: "bg-blue-100 text-blue-800",
  new: "bg-blue-100 text-blue-800",
  ordered: "bg-indigo-100 text-indigo-800",
  contacted: "bg-indigo-100 text-indigo-800",
  trial_attended: "bg-indigo-100 text-indigo-800",
  frozen: "bg-amber-100 text-amber-800",
  late: "bg-amber-100 text-amber-800",
  draft: "bg-amber-100 text-amber-800",
  pending: "bg-amber-100 text-amber-800",
  deferred: "bg-amber-100 text-amber-800",
  open: "bg-amber-100 text-amber-800",
  excused: "bg-gray-100 text-gray-700",
  inactive: "bg-gray-100 text-gray-700",
  cancelled: "bg-red-100 text-red-800",
  rejected: "bg-red-100 text-red-800",
  absent: "bg-red-100 text-red-800",
  fail: "bg-red-100 text-red-800",
  lost: "bg-red-100 text-red-800",
  expired: "bg-red-100 text-red-800",
  lapsed: "bg-red-100 text-red-800",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={cn("border-0", TONES[status] ?? "bg-gray-100 text-gray-700")}>
      {labelize(status)}
    </Badge>
  );
}

export function BeltSwatch({ color, name }: { color: string; name: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="h-3 w-6 rounded-sm border border-gray-300" style={{ backgroundColor: color }} />
      {name}
    </span>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="text-sm text-gray-500 py-6 text-center">{children}</p>;
}

/** Labelled form control. Wrapping in <label> ties the text to the control for assistive tech. */
export function Field({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <label className={cn("block space-y-1.5", className)}>
      <span className="text-sm font-medium leading-none">{label}</span>
      {children}
    </label>
  );
}

/** Select over a fixed list of option values (labels derived from the value). */
export function EnumSelect({
  value,
  onChange,
  options,
  placeholder,
  labels,
}: {
  value: string | undefined;
  onChange: (v: string) => void;
  options: readonly string[];
  placeholder?: string;
  labels?: Record<string, string>;
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger>
        <SelectValue placeholder={placeholder ?? "Select"} />
      </SelectTrigger>
      <SelectContent>
        {options.map((o) => (
          <SelectItem key={o} value={o}>
            {labels?.[o] ?? labelize(o)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/** Select over records with an id; value is the id as a string. */
export function RecordSelect<T extends { id: number }>({
  value,
  onChange,
  records,
  render,
  placeholder,
  allowNone,
}: {
  value: number | null | undefined;
  onChange: (v: number | null) => void;
  records: T[];
  render: (r: T) => string;
  placeholder?: string;
  allowNone?: string;
}) {
  return (
    <Select
      value={value ? String(value) : allowNone ? "none" : undefined}
      onValueChange={(v) => onChange(v === "none" ? null : Number(v))}
    >
      <SelectTrigger>
        <SelectValue placeholder={placeholder ?? "Select"} />
      </SelectTrigger>
      <SelectContent>
        {allowNone && <SelectItem value="none">{allowNone}</SelectItem>}
        {records.map((r) => (
          <SelectItem key={r.id} value={String(r.id)}>
            {render(r)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
