import { useEffect, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link, useLocation } from "wouter";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, Plus, Search } from "lucide-react";
import { Page } from "@/components/layout/page";
import { BeltSwatch, Empty, EnumSelect, Loading, StatusBadge } from "@/components/common";
import { MemberForm, toPayload } from "@/components/common/member-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useApiMutation } from "@/hooks/useApiMutation";
import { useAuth } from "@/hooks/useAuth";
import { useBranch } from "@/hooks/useBranch";
import { fmtDate } from "@/lib/format";
import { api, apiPage } from "@/lib/queryClient";
import type { Member } from "@/lib/types";

type SortKey = "member_no" | "name" | "age" | "belt" | "joined_on" | "standing";
const PAGE_SIZES = ["25", "50", "100", "200"];
const STANDING_LABELS = {
  all: "All members",
  active: "Active (covered today)",
  lapsed: "Lapsed",
  new: "New (no membership yet)",
  frozen: "Frozen",
  inactive: "Inactive",
};

function SortHeader({
  label,
  column,
  sort,
  order,
  onSort,
}: {
  label: string;
  column: SortKey;
  sort: SortKey;
  order: "asc" | "desc";
  onSort: (c: SortKey) => void;
}) {
  const active = sort === column;
  const Icon = !active ? ArrowUpDown : order === "asc" ? ArrowUp : ArrowDown;
  return (
    <TableHead aria-sort={active ? (order === "asc" ? "ascending" : "descending") : "none"}>
      <button className="inline-flex items-center gap-1 hover:text-foreground" onClick={() => onSort(column)}>
        {label}
        <Icon className={`h-3 w-3 ${active ? "text-brand" : "text-muted-foreground/70"}`} />
      </button>
    </TableHead>
  );
}

export default function Members() {
  const { branchId } = useBranch();
  const { isStaff } = useAuth();
  const [, setLocation] = useLocation();
  const [q, setQ] = useState("");
  const [standing, setStanding] = useState("all");
  const [sort, setSort] = useState<SortKey>("name");
  const [order, setOrder] = useState<"asc" | "desc">("asc");
  const [pageSize, setPageSize] = useState("50");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);

  // Any change to what is listed starts again from the first page.
  useEffect(() => setPage(1), [branchId, q, standing, sort, order, pageSize]);

  const limit = Number(pageSize);
  const params = {
    branch_id: branchId,
    q: q.trim() || undefined,
    standing: standing === "all" ? undefined : standing,
    sort,
    order,
    limit,
    offset: (page - 1) * limit,
  };
  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["/api/members", params],
    queryFn: () => apiPage<Member>("/api/members", params),
    enabled: branchId !== null,
    placeholderData: keepPreviousData,
  });
  const members = data?.rows ?? [];
  const total = data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / limit));
  const first = total === 0 ? 0 : (page - 1) * limit + 1;
  const last = Math.min(page * limit, total);

  const onSort = (column: SortKey) => {
    if (column === sort) setOrder(order === "asc" ? "desc" : "asc");
    else {
      setSort(column);
      setOrder("asc");
    }
  };
  const header = { sort, order, onSort };

  const create = useApiMutation(
    (body: Record<string, unknown>) => api<Member>("/api/members", { method: "POST", body }),
    {
      invalidate: ["/api/members", "/api/dashboard"],
      success: "Member registered",
      onSuccess: (m) => {
        setOpen(false);
        setLocation(`/members/${m.id}`);
      },
    },
  );

  return (
    <Page
      title="Members"
      actions={
        isStaff && (
          <Button onClick={() => setOpen(true)}>
            <Plus className="h-4 w-4 mr-1" /> Register member
          </Button>
        )
      }
    >
      <Card>
        <CardContent className="p-4 space-y-4">
          <div className="flex flex-wrap gap-3">
            <div className="relative flex-1 min-w-[220px]">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground/70" />
              <Input
                className="pl-9"
                placeholder="Search name, phone, member no. or civil ID"
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
            </div>
            <div className="w-56">
              <EnumSelect value={standing} onChange={setStanding} options={Object.keys(STANDING_LABELS)} labels={STANDING_LABELS} />
            </div>
          </div>
          {isLoading ? (
            <Loading />
          ) : members.length === 0 ? (
            <Empty>No members found.</Empty>
          ) : (
            <Table className={isFetching ? "opacity-70" : ""}>
              <TableHeader>
                <TableRow>
                  <SortHeader label="No." column="member_no" {...header} />
                  <SortHeader label="Name" column="name" {...header} />
                  <SortHeader label="Age" column="age" {...header} />
                  <TableHead>Phone</TableHead>
                  <SortHeader label="Belt" column="belt" {...header} />
                  <SortHeader label="Joined" column="joined_on" {...header} />
                  <SortHeader label="Standing" column="standing" {...header} />
                </TableRow>
              </TableHeader>
              <TableBody>
                {members.map((m) => (
                  <TableRow key={m.id}>
                    <TableCell className="whitespace-nowrap font-mono text-xs">{m.member_no}</TableCell>
                    <TableCell>
                      <Link href={`/members/${m.id}`} className="whitespace-nowrap text-brand hover:underline">
                        {m.full_name}
                      </Link>
                    </TableCell>
                    <TableCell>{m.age ?? "—"}</TableCell>
                    <TableCell className="whitespace-nowrap">{m.phone}</TableCell>
                    <TableCell>
                      {m.belt_rank ? (
                        <BeltSwatch color={m.belt_rank.color} name={`${m.belt_rank.name}${m.stripes ? ` +${m.stripes}` : ""}`} />
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell className="whitespace-nowrap">{fmtDate(m.joined_on)}</TableCell>
                    <TableCell>
                      <StatusBadge status={m.standing} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
            <span>
              {first}–{last} of {total} members
            </span>
            <div className="flex flex-wrap items-center gap-2 whitespace-nowrap">
              <span>Rows per page</span>
              <div className="w-20">
                <EnumSelect value={pageSize} onChange={setPageSize} options={PAGE_SIZES} labels={Object.fromEntries(PAGE_SIZES.map((n) => [n, n]))} />
              </div>
              <Button variant="outline" size="icon" disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label="Previous page">
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span>
                Page {page} of {pages}
              </span>
              <Button variant="outline" size="icon" disabled={page >= pages} onClick={() => setPage(page + 1)} aria-label="Next page">
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Register member</DialogTitle>
          </DialogHeader>
          <MemberForm
            submitLabel="Register"
            busy={create.isPending}
            onSubmit={(v) => create.mutate({ ...toPayload(v), branch_id: branchId })}
          />
        </DialogContent>
      </Dialog>
    </Page>
  );
}
