import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, Pencil, Plus, Star, Unlink } from "lucide-react";
import { Empty, EnumSelect, Field } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useApiMutation } from "@/hooks/useApiMutation";
import { useAuth } from "@/hooks/useAuth";
import { label } from "@/lib/format";
import { api } from "@/lib/queryClient";
import type { GuardianLink, Member } from "@/lib/types";

const RELATIONSHIPS = ["father", "mother", "guardian", "other"];
const blank = { full_name: "", full_name_ar: "", mobile: "", email: "", relationship: "mother", is_primary: false };

/** Who can open this member's page in the member portal: linked parents, or the member. */
export function FamilyCard({ member }: { member: Member }) {
  const { isStaff } = useAuth();
  const url = `/api/members/${member.id}/guardians`;
  const { data: links = [] } = useQuery<GuardianLink[]>({ queryKey: [url], enabled: isStaff });
  const [editing, setEditing] = useState<GuardianLink | "new" | null>(null);
  const [f, setF] = useState(blank);
  const inv = { invalidate: [url] };
  const save = useApiMutation(
    () => {
      const body = { ...f, email: f.email || null, full_name_ar: f.full_name_ar || null };
      return editing === "new"
        ? api(url, { method: "POST", body })
        : api(`${url}/${(editing as GuardianLink).guardian_id}`, { method: "PATCH", body });
    },
    { ...inv, success: "Family saved", onSuccess: () => setEditing(null) },
  );
  const unlink = useApiMutation((g: GuardianLink) => api(`${url}/${g.guardian_id}`, { method: "DELETE" }), {
    ...inv,
    success: "Unlinked",
  });
  if (!isStaff) return null;
  const adult = member.age === null || member.age >= 18;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between gap-2 text-base">
          Family and portal
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setF(blank);
              setEditing("new");
            }}
          >
            <Plus className="h-4 w-4 mr-1" /> Parent
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {links.length === 0 ? (
          <Empty>No parent or guardian linked.</Empty>
        ) : (
          links.map((g) => (
            <div key={g.guardian_id} className="rounded border p-2 space-y-1">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-medium">
                    {g.full_name}{" "}
                    {g.is_primary && (
                      <Badge variant="outline" className="ml-1 border-0 bg-primary/10 text-primary">
                        <Star className="h-3 w-3 mr-1" /> Primary
                      </Badge>
                    )}
                  </p>
                  <p className="text-muted-foreground">
                    {label(g.relationship)} · <span className="tabular">{g.mobile}</span>
                  </p>
                  {g.other_member_ids.length > 0 && (
                    <p className="text-xs text-muted-foreground">
                      Also parent of {g.other_member_ids.length} other member{g.other_member_ids.length > 1 ? "s" : ""}
                    </p>
                  )}
                </div>
                <span className="flex">
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label={`Edit ${g.full_name}`}
                    onClick={() => {
                      setF({
                        full_name: g.full_name,
                        full_name_ar: g.full_name_ar ?? "",
                        mobile: g.mobile,
                        email: g.email ?? "",
                        relationship: g.relationship,
                        is_primary: g.is_primary,
                      });
                      setEditing(g);
                    }}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button size="icon" variant="ghost" aria-label={`Unlink ${g.full_name}`} onClick={() => unlink.mutate(g)}>
                    <Unlink className="h-4 w-4" />
                  </Button>
                </span>
              </div>
            </div>
          ))
        )}
        <p className="text-xs text-muted-foreground">
          {links.length > 0
            ? "Linked parents sign in to the member portal with their mobile and a WhatsApp code."
            : adult
              ? "This member signs in to the member portal with their own mobile."
              : "Link a parent so the family can use the member portal."}{" "}
          <a href="/portal" target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-brand hover:underline">
            Member portal <ExternalLink className="h-3 w-3" />
          </a>
        </p>
      </CardContent>
      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing === "new" ? "Link a parent or guardian" : "Edit parent or guardian"}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            A parent already linked to a sibling is found by mobile, so the family shares one portal login.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Full name">
              <Input value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} />
            </Field>
            <Field label="Full name (Arabic)">
              <Input dir="rtl" value={f.full_name_ar} onChange={(e) => setF({ ...f, full_name_ar: e.target.value })} />
            </Field>
            <Field label="Mobile (Kuwait, 8 digits)">
              <Input inputMode="tel" value={f.mobile} onChange={(e) => setF({ ...f, mobile: e.target.value })} />
            </Field>
            <Field label="Relationship">
              <EnumSelect value={f.relationship} onChange={(r) => setF({ ...f, relationship: r })} options={RELATIONSHIPS} />
            </Field>
            <Field label="Email (optional)">
              <Input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
            </Field>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={f.is_primary} onCheckedChange={(c) => setF({ ...f, is_primary: !!c })} />
            Primary contact (pays and receives messages)
          </label>
          <Button disabled={!f.full_name || !f.mobile || save.isPending} onClick={() => save.mutate(undefined)}>
            Save
          </Button>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
