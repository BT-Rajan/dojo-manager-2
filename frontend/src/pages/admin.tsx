import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { KeyRound, Plus } from "lucide-react";
import { Page } from "@/components/layout/page";
import { BeltSwatch, Empty, EnumSelect, Field, RecordSelect, StatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApiMutation } from "@/hooks/useApiMutation";
import { useAuth } from "@/hooks/useAuth";
import { useBranch, useBranches } from "@/hooks/useBranch";
import { useBelts, useInstructors, usePrograms } from "@/hooks/useLookups";
import { ROLE_LABELS, fmtDateTime, kd, label } from "@/lib/format";
import { api } from "@/lib/queryClient";
import type { Branch, Plan, Role, User } from "@/lib/types";

const ROLES: Role[] = ["owner", "manager", "branch_admin", "instructor"];

function BranchChecks({ value, onChange, branches }: { value: number[]; onChange: (v: number[]) => void; branches: Branch[] }) {
  return (
    <div className="flex flex-wrap gap-4">
      {branches.map((b) => (
        <label key={b.id} className="flex items-center gap-2 text-sm">
          <Checkbox
            checked={value.includes(b.id)}
            onCheckedChange={(c) => onChange(c ? [...value, b.id] : value.filter((x) => x !== b.id))}
          />
          {b.name}
        </label>
      ))}
    </div>
  );
}

function UsersTab() {
  const { user: me } = useAuth();
  const { data: branches = [] } = useBranches();
  const { data: users = [] } = useQuery<User[]>({ queryKey: ["/api/users"] });
  const [editing, setEditing] = useState<User | "new" | null>(null);
  const [f, setF] = useState({ username: "", full_name: "", email: "", password: "", role: "branch_admin" as Role });
  const [branchIds, setBranchIds] = useState<number[]>([]);
  const [resetFor, setResetFor] = useState<User | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const inv = { invalidate: ["/api/users"] };

  const openNew = () => {
    setF({ username: "", full_name: "", email: "", password: "", role: "branch_admin" });
    setBranchIds([]);
    setEditing("new");
  };
  const openEdit = (u: User) => {
    setF({ username: u.username, full_name: u.full_name, email: u.email ?? "", password: "", role: u.role });
    setBranchIds(u.branches.map((b) => b.id));
    setEditing(u);
  };
  const save = useApiMutation(
    () =>
      editing === "new"
        ? api("/api/users", { method: "POST", body: { ...f, email: f.email || null, branch_ids: branchIds } })
        : api(`/api/users/${(editing as User).id}`, {
            method: "PATCH",
            body: { full_name: f.full_name, email: f.email || null, role: f.role, branch_ids: branchIds },
          }),
    { ...inv, success: "User saved", onSuccess: () => setEditing(null) },
  );
  const toggle = useApiMutation(
    (u: User) => api(`/api/users/${u.id}`, { method: "PATCH", body: { is_active: !u.is_active } }),
    inv,
  );
  const reset = useApiMutation(
    () => api(`/api/users/${resetFor?.id}/reset-password`, { method: "POST", body: { password: newPassword } }),
    { success: "Password reset; the user's sessions were signed out", onSuccess: () => setResetFor(null) },
  );

  return (
    <div className="space-y-4">
      <Button onClick={openNew}>
        <Plus className="h-4 w-4 mr-1" /> New user
      </Button>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Username</TableHead>
            <TableHead>Role</TableHead>
            <TableHead>Branches</TableHead>
            <TableHead>Last login</TableHead>
            <TableHead>Active</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {users.map((u) => (
            <TableRow key={u.id}>
              <TableCell>
                <button className="text-brand hover:underline" onClick={() => openEdit(u)}>
                  {u.full_name}
                </button>
              </TableCell>
              <TableCell className="font-mono text-xs">{u.username}</TableCell>
              <TableCell>{ROLE_LABELS[u.role]}</TableCell>
              <TableCell>{u.role === "owner" || u.role === "manager" ? "All" : u.branches.map((b) => b.name).join(", ") || "—"}</TableCell>
              <TableCell>{fmtDateTime(u.last_login_at)}</TableCell>
              <TableCell>
                <Switch checked={u.is_active} disabled={u.id === me?.id} onCheckedChange={() => toggle.mutate(u)} aria-label="Active" />
              </TableCell>
              <TableCell>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setNewPassword("");
                    setResetFor(u);
                  }}
                  aria-label="Reset password"
                >
                  <KeyRound className="h-4 w-4" />
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing === "new" ? "New user" : "Edit user"}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Full name">
              <Input value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} />
            </Field>
            <Field label="Email">
              <Input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
            </Field>
            {editing === "new" && (
              <>
                <Field label="Username">
                  <Input value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} />
                </Field>
                <Field label="Password (10+ characters)">
                  <Input type="password" autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
                </Field>
              </>
            )}
            <Field label="Role" className="sm:col-span-2">
              <EnumSelect value={f.role} onChange={(r) => setF({ ...f, role: r as Role })} options={ROLES} labels={ROLE_LABELS} />
            </Field>
          </div>
          {(f.role === "branch_admin" || f.role === "instructor") && (
            <Field label="Branch access">
              <BranchChecks value={branchIds} onChange={setBranchIds} branches={branches} />
            </Field>
          )}
          <Button disabled={!f.full_name || save.isPending} onClick={() => save.mutate(undefined)}>
            Save
          </Button>
        </DialogContent>
      </Dialog>
      <Dialog open={!!resetFor} onOpenChange={(o) => !o && setResetFor(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reset password for {resetFor?.full_name}</DialogTitle>
          </DialogHeader>
          <Field label="New password (10+ characters)">
            <Input type="password" autoComplete="new-password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
          </Field>
          <Button disabled={newPassword.length < 10 || reset.isPending} onClick={() => reset.mutate(undefined)}>
            Reset password
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function BranchesTab() {
  const { data: branches = [] } = useBranches();
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ name: "", code: "", address: "", phone: "" });
  const create = useApiMutation(
    () => api("/api/branches", { method: "POST", body: { ...f, address: f.address || null, phone: f.phone || null } }),
    { invalidate: ["/api/branches"], success: "Branch added", onSuccess: () => setOpen(false) },
  );
  return (
    <div className="space-y-4">
      <Button onClick={() => setOpen(true)}>
        <Plus className="h-4 w-4 mr-1" /> New branch
      </Button>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Code</TableHead>
            <TableHead>Address</TableHead>
            <TableHead>Phone</TableHead>
            <TableHead>Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {branches.map((b) => (
            <TableRow key={b.id}>
              <TableCell>{b.name}</TableCell>
              <TableCell className="font-mono text-xs">{b.code}</TableCell>
              <TableCell>{b.address ?? "—"}</TableCell>
              <TableCell>{b.phone ?? "—"}</TableCell>
              <TableCell>
                <StatusBadge status={b.is_active ? "active" : "inactive"} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New branch</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Name">
              <Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
            </Field>
            <Field label="Code (e.g. PRM)">
              <Input value={f.code} onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase() })} />
            </Field>
            <Field label="Address">
              <Input value={f.address} onChange={(e) => setF({ ...f, address: e.target.value })} />
            </Field>
            <Field label="Phone">
              <Input value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} />
            </Field>
          </div>
          <Button disabled={!f.name || !f.code || create.isPending} onClick={() => create.mutate(undefined)}>
            Save
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function InstructorsTab() {
  const { branchId, branch } = useBranch();
  const { belts, beltMap } = useBelts();
  const { instructors } = useInstructors(branchId);
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ full_name: "", phone: "", email: "", specialties: "" });
  const [belt, setBelt] = useState<number | null>(null);
  const inv = { invalidate: ["/api/instructors"] };
  const create = useApiMutation(
    () =>
      api("/api/instructors", {
        method: "POST",
        body: {
          branch_id: branchId,
          full_name: f.full_name,
          phone: f.phone || null,
          email: f.email || null,
          specialties: f.specialties || null,
          belt_rank_id: belt,
        },
      }),
    { ...inv, success: "Instructor added", onSuccess: () => setOpen(false) },
  );
  const toggle = useApiMutation(
    ({ id, active }: { id: number; active: boolean }) => api(`/api/instructors/${id}`, { method: "PATCH", body: { is_active: active } }),
    inv,
  );
  if (!branchId) return <Empty>Choose a branch first.</Empty>;
  return (
    <div className="space-y-4">
      <Button onClick={() => setOpen(true)}>
        <Plus className="h-4 w-4 mr-1" /> New instructor at {branch?.name}
      </Button>
      {instructors.length === 0 ? (
        <Empty>No instructors at this branch.</Empty>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Specialties</TableHead>
              <TableHead>Rank</TableHead>
              <TableHead>Phone</TableHead>
              <TableHead>Active</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {instructors.map((i) => {
              const b = i.belt_rank_id ? beltMap.get(i.belt_rank_id) : undefined;
              return (
                <TableRow key={i.id}>
                  <TableCell>{i.full_name}</TableCell>
                  <TableCell>{i.specialties ?? "—"}</TableCell>
                  <TableCell>{b ? <BeltSwatch color={b.color} name={b.name} /> : "—"}</TableCell>
                  <TableCell>{i.phone ?? "—"}</TableCell>
                  <TableCell>
                    <Switch checked={i.is_active} onCheckedChange={(c) => toggle.mutate({ id: i.id, active: c })} aria-label="Active" />
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New instructor</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Full name">
              <Input value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} />
            </Field>
            <Field label="Specialties">
              <Input placeholder="Kickboxing, BJJ…" value={f.specialties} onChange={(e) => setF({ ...f, specialties: e.target.value })} />
            </Field>
            <Field label="Phone">
              <Input value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} />
            </Field>
            <Field label="Email">
              <Input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
            </Field>
            <Field label="Rank" className="sm:col-span-2">
              <RecordSelect value={belt} onChange={setBelt} records={belts} render={(b) => b.name} allowNone="—" />
            </Field>
          </div>
          <Button disabled={!f.full_name || create.isPending} onClick={() => create.mutate(undefined)}>
            Save
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function CatalogTab() {
  const { programs } = usePrograms();
  const { belts } = useBelts();
  const { data: branches = [] } = useBranches();
  const { data: plans = [] } = useQuery<Plan[]>({ queryKey: ["/api/plans"] });
  const [open, setOpen] = useState<"program" | "plan" | null>(null);
  const [p, setP] = useState({ name: "", discipline: "kajukenbo", min_age: "", max_age: "" });
  const [plan, setPlan] = useState({ name: "", duration_days: "30", price: "" });
  const [planBranch, setPlanBranch] = useState<number | null>(null);
  const createProgram = useApiMutation(
    () =>
      api("/api/programs", {
        method: "POST",
        body: { name: p.name, discipline: p.discipline, min_age: p.min_age ? Number(p.min_age) : null, max_age: p.max_age ? Number(p.max_age) : null },
      }),
    { invalidate: ["/api/programs"], success: "Programme added", onSuccess: () => setOpen(null) },
  );
  const createPlan = useApiMutation(
    () =>
      api("/api/plans", {
        method: "POST",
        body: { name: plan.name, duration_days: Number(plan.duration_days), price: plan.price, branch_id: planBranch },
      }),
    { invalidate: ["/api/plans"], success: "Plan added", onSuccess: () => setOpen(null) },
  );
  const togglePlan = useApiMutation(
    (pl: Plan) => api(`/api/plans/${pl.id}`, { method: "PATCH", body: { is_active: !pl.is_active } }),
    { invalidate: ["/api/plans"] },
  );
  const branchName = (id: number | null) => (id ? branches.find((b) => b.id === id)?.name : "All branches");

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">Membership plans</h3>
          <Button size="sm" variant="outline" onClick={() => setOpen("plan")}>
            <Plus className="h-4 w-4 mr-1" /> Plan
          </Button>
        </div>
        <Table>
          <TableBody>
            {plans.map((pl) => (
              <TableRow key={pl.id}>
                <TableCell>
                  {pl.name}
                  <div className="text-xs text-muted-foreground">
                    {branchName(pl.branch_id)} · {pl.duration_days} days
                  </div>
                </TableCell>
                <TableCell className="text-right">{kd(pl.price)}</TableCell>
                <TableCell>
                  <Switch checked={pl.is_active} onCheckedChange={() => togglePlan.mutate(pl)} aria-label="Active" />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <div className="flex items-center justify-between pt-4">
          <h3 className="font-semibold">Programmes</h3>
          <Button size="sm" variant="outline" onClick={() => setOpen("program")}>
            <Plus className="h-4 w-4 mr-1" /> Programme
          </Button>
        </div>
        <Table>
          <TableBody>
            {programs.map((pr) => (
              <TableRow key={pr.id}>
                <TableCell>{pr.name}</TableCell>
                <TableCell>{label(pr.discipline)}</TableCell>
                <TableCell>
                  {pr.min_age ?? ""}
                  {pr.min_age || pr.max_age ? "–" : ""}
                  {pr.max_age ?? (pr.min_age ? "+" : "All ages")}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <div className="space-y-3">
        <h3 className="font-semibold">Belt system</h3>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Belt</TableHead>
              <TableHead>Grappling stripe</TableHead>
              <TableHead>BJJ equivalent</TableHead>
              <TableHead className="text-right">Seminars</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {belts.map((b) => (
              <TableRow key={b.id}>
                <TableCell>
                  <BeltSwatch color={b.color} name={b.name} />
                  <div className="text-xs text-muted-foreground">{label(b.phase)}</div>
                </TableCell>
                <TableCell>{b.bjj_stripe ?? "—"}</TableCell>
                <TableCell>{b.bjj_equivalent ?? "—"}</TableCell>
                <TableCell className="text-right">{b.seminars_required}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <Dialog open={open === "program"} onOpenChange={(o) => !o && setOpen(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New programme</DialogTitle>
          </DialogHeader>
          <Field label="Name">
            <Input value={p.name} onChange={(e) => setP({ ...p, name: e.target.value })} />
          </Field>
          <Field label="Discipline">
            <EnumSelect
              value={p.discipline}
              onChange={(d) => setP({ ...p, discipline: d })}
              options={["kajukenbo", "kickboxing", "jiujitsu", "self_defence", "fitness", "open_mat", "other"]}
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Min age">
              <Input type="number" value={p.min_age} onChange={(e) => setP({ ...p, min_age: e.target.value })} />
            </Field>
            <Field label="Max age">
              <Input type="number" value={p.max_age} onChange={(e) => setP({ ...p, max_age: e.target.value })} />
            </Field>
          </div>
          <Button disabled={!p.name || createProgram.isPending} onClick={() => createProgram.mutate(undefined)}>
            Save
          </Button>
        </DialogContent>
      </Dialog>
      <Dialog open={open === "plan"} onOpenChange={(o) => !o && setOpen(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New membership plan</DialogTitle>
          </DialogHeader>
          <Field label="Name">
            <Input value={plan.name} onChange={(e) => setPlan({ ...plan, name: e.target.value })} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Days">
              <Input type="number" min={1} value={plan.duration_days} onChange={(e) => setPlan({ ...plan, duration_days: e.target.value })} />
            </Field>
            <Field label="Price (KD)">
              <Input inputMode="decimal" value={plan.price} onChange={(e) => setPlan({ ...plan, price: e.target.value })} />
            </Field>
          </div>
          <Field label="Branch">
            <RecordSelect value={planBranch} onChange={setPlanBranch} records={branches} render={(b) => b.name} allowNone="All branches" />
          </Field>
          <Button disabled={!plan.name || !plan.price || createPlan.isPending} onClick={() => createPlan.mutate(undefined)}>
            Save
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function Admin() {
  const { isOwner, isManagement } = useAuth();
  if (!isManagement) {
    return (
      <Page title="Admin" needsBranch={false}>
        <Empty>Only the owner and operations manager can open this page.</Empty>
      </Page>
    );
  }
  return (
    <Page title="Admin" subtitle="Academy settings" needsBranch={false}>
      <Tabs defaultValue={isOwner ? "users" : "catalog"}>
        <TabsList className="flex-wrap h-auto">
          {isOwner && <TabsTrigger value="users">Users</TabsTrigger>}
          {isOwner && <TabsTrigger value="branches">Branches</TabsTrigger>}
          <TabsTrigger value="instructors">Instructors</TabsTrigger>
          <TabsTrigger value="catalog">Plans, programmes & belts</TabsTrigger>
        </TabsList>
        {isOwner && (
          <TabsContent value="users">
            <UsersTab />
          </TabsContent>
        )}
        {isOwner && (
          <TabsContent value="branches">
            <BranchesTab />
          </TabsContent>
        )}
        <TabsContent value="instructors">
          <InstructorsTab />
        </TabsContent>
        <TabsContent value="catalog">
          <CatalogTab />
        </TabsContent>
      </Tabs>
    </Page>
  );
}
