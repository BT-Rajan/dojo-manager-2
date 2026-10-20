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
          <p className="text-sm text-muted-foreground">{title}</p>
          <p className="text-2xl font-bold text-foreground">{value}</p>
          {hint && <p className="text-xs text-muted-foreground/70 mt-1">{hint}</p>}
        </div>
        <Icon className={cn("h-8 w-8", tone)} />
      </CardContent>
    </Card>
  );
}

const TONES: Record<string, string> = {
  active: "bg-success/15 text-success",
  approved: "bg-success/15 text-success",
  received: "bg-success/15 text-success",
  present: "bg-success/15 text-success",
  pass: "bg-success/15 text-success",
  converted: "bg-success/15 text-success",
  completed: "bg-success/15 text-success",
  closed: "bg-muted text-foreground/80",
  scheduled: "bg-info/15 text-info",
  booked: "bg-info/15 text-info",
  planned: "bg-info/15 text-info",
  submitted: "bg-info/15 text-info",
  in_transit: "bg-info/15 text-info",
  trial_booked: "bg-info/15 text-info",
  new: "bg-info/15 text-info",
  ordered: "bg-accent-purple/15 text-accent-purple",
  contacted: "bg-accent-purple/15 text-accent-purple",
  trial_attended: "bg-accent-purple/15 text-accent-purple",
  frozen: "bg-warning/15 text-warning",
  late: "bg-warning/15 text-warning",
  draft: "bg-warning/15 text-warning",
  pending: "bg-warning/15 text-warning",
  deferred: "bg-warning/15 text-warning",
  open: "bg-warning/15 text-warning",
  excused: "bg-muted text-foreground/80",
  inactive: "bg-muted text-foreground/80",
  cancelled: "bg-destructive/15 text-destructive",
  rejected: "bg-destructive/15 text-destructive",
  absent: "bg-destructive/15 text-destructive",
  fail: "bg-destructive/15 text-destructive",
  lost: "bg-destructive/15 text-destructive",
  expired: "bg-destructive/15 text-destructive",
  lapsed: "bg-destructive/15 text-destructive",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={cn("border-0", TONES[status] ?? "bg-muted text-foreground/80")}>
      {labelize(status)}
    </Badge>
  );
}

export function BeltSwatch({ color, name }: { color: string; name: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="h-3 w-6 rounded-sm border border-border" style={{ backgroundColor: color }} />
      {name}
    </span>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="text-sm text-muted-foreground py-6 text-center">{children}</p>;
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
