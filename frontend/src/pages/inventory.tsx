import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { format } from "date-fns";
import { Plus, ShoppingCart, Trash2 } from "lucide-react";
import { Page } from "@/components/layout/page";
import { Empty, EnumSelect, Field, RecordSelect, StatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApiMutation } from "@/hooks/useApiMutation";
import { useAuth } from "@/hooks/useAuth";
import { useBranch } from "@/hooks/useBranch";
import { useItems } from "@/hooks/useLookups";
import { fmtDateTime, kd, label } from "@/lib/format";
import { api } from "@/lib/queryClient";
import type { Item, Line, PurchaseRequest, StockCount, StockRow, Transfer } from "@/lib/types";

const itemLabel = (i: Item) => `${i.name}${i.size ? ` (${i.size})` : ""} · ${i.sku}`;

function useStock() {
  const { branchId } = useBranch();
  return useQuery<StockRow[]>({
    queryKey: ["/api/inventory/stock", { branch_id: branchId }],
    enabled: branchId !== null,
  }).data ?? [];
}

function LineEditor({ lines, onChange }: { lines: Line[]; onChange: (l: Line[]) => void }) {
  const { items } = useItems();
  return (
    <div className="space-y-2">
      {lines.map((ln, i) => (
        <div key={i} className="flex gap-2">
          <div className="flex-1">
            <RecordSelect
              value={ln.item_id || null}
              onChange={(id) => onChange(lines.map((l, j) => (j === i ? { ...l, item_id: id ?? 0 } : l)))}
              records={items}
              render={itemLabel}
              placeholder="Item"
            />
          </div>
          <Input
            type="number"
            min={1}
            className="w-24"
            aria-label="Quantity"
            value={ln.quantity}
            onChange={(e) => onChange(lines.map((l, j) => (j === i ? { ...l, quantity: Number(e.target.value) } : l)))}
          />
          <Button variant="ghost" size="icon" onClick={() => onChange(lines.filter((_, j) => j !== i))} aria-label="Remove line">
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      ))}
      <Button variant="outline" size="sm" onClick={() => onChange([...lines, { item_id: 0, quantity: 1 }])}>
        <Plus className="h-4 w-4 mr-1" /> Add item
      </Button>
    </div>
  );
}

const validLines = (lines: Line[]) => lines.length > 0 && lines.every((l) => l.item_id > 0 && l.quantity > 0);

function StockTab() {
  const { branchId } = useBranch();
  const { isManagement } = useAuth();
  const stock = useStock();
  const [lowOnly, setLowOnly] = useState(false);
  const [selling, setSelling] = useState<StockRow | null>(null);
  const [sale, setSale] = useState({ quantity: "1", method: "knet" });
  const [newItem, setNewItem] = useState(false);
  const [item, setItem] = useState({ sku: "", name: "", category: "uniform", size: "", unit_price: "", reorder_level: "0" });
  const sell = useApiMutation(
    () =>
      api("/api/inventory/sales", {
        method: "POST",
        body: { branch_id: branchId, item_id: selling?.item.id, quantity: Number(sale.quantity), method: sale.method },
      }),
    { invalidate: ["/api/inventory", "/api/payments", "/api/dashboard"], success: "Sale recorded", onSuccess: () => setSelling(null) },
  );
  const createItem = useApiMutation(
    () =>
      api("/api/inventory/items", {
        method: "POST",
        body: { ...item, size: item.size || null, reorder_level: Number(item.reorder_level) },
      }),
    { invalidate: ["/api/inventory"], success: "Item added", onSuccess: () => setNewItem(false) },
  );
  const rows = lowOnly ? stock.filter((s) => s.below_reorder) : stock;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2 text-sm">
          <Checkbox checked={lowOnly} onCheckedChange={(c) => setLowOnly(c === true)} /> Low stock only
        </label>
        {isManagement && (
          <Button variant="outline" size="sm" onClick={() => setNewItem(true)}>
            <Plus className="h-4 w-4 mr-1" /> New item
          </Button>
        )}
      </div>
      {rows.length === 0 ? (
        <Empty>No items.</Empty>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Item</TableHead>
              <TableHead>Category</TableHead>
              <TableHead className="text-right">Price</TableHead>
              <TableHead className="text-right">On hand</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((s) => (
              <TableRow key={s.item.id}>
                <TableCell>{itemLabel(s.item)}</TableCell>
                <TableCell>{label(s.item.category)}</TableCell>
                <TableCell className="text-right">{kd(s.item.unit_price)}</TableCell>
                <TableCell className={`text-right font-medium ${s.below_reorder ? "text-red-600" : ""}`}>{s.quantity}</TableCell>
                <TableCell className="text-right">
                  <Button size="sm" variant="outline" disabled={s.quantity === 0} onClick={() => setSelling(s)}>
                    <ShoppingCart className="h-4 w-4 mr-1" /> Sell
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <Dialog open={!!selling} onOpenChange={(o) => !o && setSelling(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Sell {selling && itemLabel(selling.item)}</DialogTitle>
          </DialogHeader>
          <Field label={`Quantity (${selling?.quantity} on hand)`}>
            <Input type="number" min={1} max={selling?.quantity} value={sale.quantity} onChange={(e) => setSale({ ...sale, quantity: e.target.value })} />
          </Field>
          <Field label="Payment method">
            <EnumSelect value={sale.method} onChange={(m) => setSale({ ...sale, method: m })} options={["knet", "card", "cash"]} labels={{ knet: "KNET", card: "Visa / Mastercard" }} />
          </Field>
          <p className="text-sm">Total: {selling && kd(Number(selling.item.unit_price) * Number(sale.quantity || 0))}</p>
          <Button disabled={sell.isPending} onClick={() => sell.mutate(undefined)}>
            Record sale
          </Button>
        </DialogContent>
      </Dialog>
      <Dialog open={newItem} onOpenChange={setNewItem}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New inventory item</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="SKU">
              <Input value={item.sku} onChange={(e) => setItem({ ...item, sku: e.target.value })} />
            </Field>
            <Field label="Name">
              <Input value={item.name} onChange={(e) => setItem({ ...item, name: e.target.value })} />
            </Field>
            <Field label="Category">
              <EnumSelect
                value={item.category}
                onChange={(c) => setItem({ ...item, category: c })}
                options={["uniform", "belt", "protective_gear", "training_equipment", "merchandise", "other"]}
              />
            </Field>
            <Field label="Size">
              <Input value={item.size} onChange={(e) => setItem({ ...item, size: e.target.value })} />
            </Field>
            <Field label="Price (KD)">
              <Input inputMode="decimal" value={item.unit_price} onChange={(e) => setItem({ ...item, unit_price: e.target.value })} />
            </Field>
            <Field label="Reorder level">
              <Input type="number" min={0} value={item.reorder_level} onChange={(e) => setItem({ ...item, reorder_level: e.target.value })} />
            </Field>
          </div>
          <Button disabled={!item.sku || !item.name || !item.unit_price || createItem.isPending} onClick={() => createItem.mutate(undefined)}>
            Save
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function PurchasingTab() {
  const { branchId } = useBranch();
  const { isManagement } = useAuth();
  const { itemMap } = useItems();
  const [creating, setCreating] = useState(false);
  const [vendor, setVendor] = useState({ vendor_name: "", vendor_type: "international", notes: "" });
  const [lines, setLines] = useState<Line[]>([{ item_id: 0, quantity: 1 }]);
  const [receiving, setReceiving] = useState<PurchaseRequest | null>(null);
  const [received, setReceived] = useState<Record<number, number>>({});
  const [invoice, setInvoice] = useState("");
  const [rejectNote, setRejectNote] = useState<Record<number, string>>({});
  const { data: requests = [] } = useQuery<PurchaseRequest[]>({
    queryKey: ["/api/inventory/purchase-requests", { branch_id: branchId }],
    enabled: branchId !== null,
  });
  const inv = { invalidate: ["/api/inventory"] };
  const create = useApiMutation(
    () =>
      api("/api/inventory/purchase-requests", {
        method: "POST",
        body: { ...vendor, notes: vendor.notes || null, branch_id: branchId, lines },
      }),
    { ...inv, success: "Purchase request saved as draft", onSuccess: () => setCreating(false) },
  );
  const act = useApiMutation(
    ({ id, step, body }: { id: number; step: string; body?: unknown }) =>
      api(`/api/inventory/purchase-requests/${id}/${step}`, { method: "POST", body }),
    inv,
  );
  const receive = useApiMutation(
    () =>
      api("/api/inventory/receipts", {
        method: "POST",
        body: {
          branch_id: receiving?.branch_id,
          purchase_request_id: receiving?.id,
          vendor_invoice_no: invoice || null,
          lines: receiving?.lines.map((l) => ({ item_id: l.item_id, qty_received: received[l.item_id] ?? l.quantity })),
        },
      }),
    { ...inv, success: "Delivery received into stock", onSuccess: () => setReceiving(null) },
  );

  return (
    <div className="space-y-4">
      <Button
        onClick={() => {
          setLines([{ item_id: 0, quantity: 1 }]);
          setCreating(true);
        }}
      >
        <Plus className="h-4 w-4 mr-1" /> New purchase request
      </Button>
      {requests.length === 0 ? (
        <Empty>No purchase requests.</Empty>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Ref</TableHead>
              <TableHead>Vendor</TableHead>
              <TableHead>Items</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {requests.map((r) => (
              <TableRow key={r.id}>
                <TableCell className="font-mono text-xs">{r.ref_no}</TableCell>
                <TableCell>
                  {r.vendor_name}
                  <div className="text-xs text-gray-500">{label(r.vendor_type)}</div>
                </TableCell>
                <TableCell className="text-sm">
                  {r.lines.map((l) => (
                    <div key={l.id}>
                      {l.quantity} × {itemMap.get(l.item_id)?.name} {itemMap.get(l.item_id)?.size}
                    </div>
                  ))}
                </TableCell>
                <TableCell>
                  <StatusBadge status={r.status} />
                  {r.decision_note && <div className="text-xs text-gray-500">{r.decision_note}</div>}
                </TableCell>
                <TableCell className="text-right space-y-1">
                  {r.status === "draft" && (
                    <Button size="sm" onClick={() => act.mutate({ id: r.id, step: "submit" })}>
                      Submit for approval
                    </Button>
                  )}
                  {r.status === "submitted" && isManagement && (
                    <div className="flex flex-col gap-1 items-end">
                      <Button size="sm" onClick={() => act.mutate({ id: r.id, step: "decision", body: { approve: true } })}>
                        Approve
                      </Button>
                      <div className="flex gap-1">
                        <Input
                          className="h-8 w-40"
                          placeholder="Reason"
                          value={rejectNote[r.id] ?? ""}
                          onChange={(e) => setRejectNote({ ...rejectNote, [r.id]: e.target.value })}
                        />
                        <Button
                          size="sm"
                          variant="destructive"
                          disabled={!rejectNote[r.id]}
                          onClick={() => act.mutate({ id: r.id, step: "decision", body: { approve: false, note: rejectNote[r.id] } })}
                        >
                          Reject
                        </Button>
                      </div>
                    </div>
                  )}
                  {r.status === "approved" && (
                    <Button size="sm" variant="outline" onClick={() => act.mutate({ id: r.id, step: "ordered" })}>
                      Mark ordered
                    </Button>
                  )}
                  {(r.status === "approved" || r.status === "ordered") && (
                    <Button
                      size="sm"
                      onClick={() => {
                        setReceived({});
                        setInvoice("");
                        setReceiving(r);
                      }}
                    >
                      Receive delivery
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>New purchase request</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Vendor">
              <Input value={vendor.vendor_name} onChange={(e) => setVendor({ ...vendor, vendor_name: e.target.value })} />
            </Field>
            <Field label="Vendor type">
              <EnumSelect value={vendor.vendor_type} onChange={(t) => setVendor({ ...vendor, vendor_type: t })} options={["international", "local"]} />
            </Field>
          </div>
          {vendor.vendor_type === "local" && (
            <p className="text-xs text-amber-700">Local-vendor purchases are limited to one per branch per month.</p>
          )}
          <LineEditor lines={lines} onChange={setLines} />
          <Button disabled={!vendor.vendor_name || !validLines(lines) || create.isPending} onClick={() => create.mutate(undefined)}>
            Save draft
          </Button>
        </DialogContent>
      </Dialog>
      <Dialog open={!!receiving} onOpenChange={(o) => !o && setReceiving(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Receive {receiving?.ref_no}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-gray-500">Count every item and size against the invoice. Enter what actually arrived.</p>
          <Field label="Vendor invoice no.">
            <Input value={invoice} onChange={(e) => setInvoice(e.target.value)} />
          </Field>
          {receiving?.lines.map((l) => (
            <div key={l.id} className="flex items-center justify-between gap-2 text-sm">
              <span>
                {itemMap.get(l.item_id)?.name} {itemMap.get(l.item_id)?.size} <span className="text-gray-400">(ordered {l.quantity})</span>
              </span>
              <Input
                type="number"
                min={0}
                className="w-24"
                aria-label="Received"
                value={received[l.item_id] ?? l.quantity}
                onChange={(e) => setReceived({ ...received, [l.item_id]: Number(e.target.value) })}
              />
            </div>
          ))}
          <Button disabled={receive.isPending} onClick={() => receive.mutate(undefined)}>
            Confirm receipt
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function TransfersTab() {
  const { branchId } = useBranch();
  const { itemMap } = useItems();
  const [creating, setCreating] = useState(false);
  const [toBranch, setToBranch] = useState<number | null>(null);
  const [lines, setLines] = useState<Line[]>([{ item_id: 0, quantity: 1 }]);
  const { data: transfers = [] } = useQuery<Transfer[]>({ queryKey: ["/api/inventory/transfers"] });
  const { data: allBranches = [] } = useQuery<{ id: number; name: string }[]>({ queryKey: ["/api/branches/directory"] });
  const branchName = (id: number) => allBranches.find((b) => b.id === id)?.name ?? `#${id}`;
  const inv = { invalidate: ["/api/inventory"] };
  const send = useApiMutation(
    () => api("/api/inventory/transfers", { method: "POST", body: { from_branch_id: branchId, to_branch_id: toBranch, lines } }),
    { ...inv, success: "Transfer sent", onSuccess: () => setCreating(false) },
  );
  const act = useApiMutation(
    ({ id, step }: { id: number; step: "receive" | "cancel" }) => api(`/api/inventory/transfers/${id}/${step}`, { method: "POST" }),
    inv,
  );
  const mine = transfers.filter((t) => t.from_branch_id === branchId || t.to_branch_id === branchId);

  return (
    <div className="space-y-4">
      <Button onClick={() => setCreating(true)}>
        <Plus className="h-4 w-4 mr-1" /> Send items to another branch
      </Button>
      {mine.length === 0 ? (
        <Empty>No transfers.</Empty>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Ref</TableHead>
              <TableHead>From → To</TableHead>
              <TableHead>Items</TableHead>
              <TableHead>Sent</TableHead>
              <TableHead>Status</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {mine.map((t) => (
              <TableRow key={t.id}>
                <TableCell className="font-mono text-xs">{t.ref_no}</TableCell>
                <TableCell>
                  {branchName(t.from_branch_id)} → {branchName(t.to_branch_id)}
                </TableCell>
                <TableCell className="text-sm">
                  {t.lines.map((l) => (
                    <div key={l.item_id}>
                      {l.quantity} × {itemMap.get(l.item_id)?.name} {itemMap.get(l.item_id)?.size}
                    </div>
                  ))}
                </TableCell>
                <TableCell>{fmtDateTime(t.sent_at)}</TableCell>
                <TableCell>
                  <StatusBadge status={t.status} />
                </TableCell>
                <TableCell className="text-right">
                  {t.status === "in_transit" && t.to_branch_id === branchId && (
                    <Button size="sm" onClick={() => act.mutate({ id: t.id, step: "receive" })}>
                      Sign for receipt
                    </Button>
                  )}
                  {t.status === "in_transit" && t.from_branch_id === branchId && (
                    <Button size="sm" variant="ghost" onClick={() => act.mutate({ id: t.id, step: "cancel" })}>
                      Cancel
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Internal transfer</DialogTitle>
          </DialogHeader>
          <Field label="Send to">
            <RecordSelect
              value={toBranch}
              onChange={setToBranch}
              records={allBranches.filter((b) => b.id !== branchId)}
              render={(b) => b.name}
            />
          </Field>
          <LineEditor lines={lines} onChange={setLines} />
          <Button disabled={!toBranch || !validLines(lines) || send.isPending} onClick={() => send.mutate(undefined)}>
            Send
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function CountsTab() {
  const { branchId } = useBranch();
  const { isManagement } = useAuth();
  const { itemMap } = useItems();
  const stock = useStock();
  const [counting, setCounting] = useState(false);
  const [period, setPeriod] = useState(format(new Date(), "yyyy-MM"));
  const [counted, setCounted] = useState<Record<number, { qty: string; reason: string }>>({});
  const { data: counts = [] } = useQuery<StockCount[]>({
    queryKey: ["/api/inventory/counts", { branch_id: branchId }],
    enabled: branchId !== null,
  });
  const inv = { invalidate: ["/api/inventory"] };
  const save = useApiMutation(
    () =>
      api("/api/inventory/counts", {
        method: "POST",
        body: {
          branch_id: branchId,
          period,
          lines: stock.map((s) => ({
            item_id: s.item.id,
            counted_qty: Number(counted[s.item.id]?.qty ?? s.quantity),
            reason: counted[s.item.id]?.reason || null,
          })),
        },
      }),
    { ...inv, success: "Count saved — awaiting manager approval", onSuccess: () => setCounting(false) },
  );
  const approve = useApiMutation((id: number) => api(`/api/inventory/counts/${id}/approve`, { method: "POST" }), {
    ...inv,
    success: "Count approved; stock adjusted",
  });

  return (
    <div className="space-y-4">
      <Button
        onClick={() => {
          setCounted({});
          setCounting(true);
        }}
      >
        <Plus className="h-4 w-4 mr-1" /> Start monthly count
      </Button>
      {counts.length === 0 ? (
        <Empty>No counts recorded.</Empty>
      ) : (
        counts.map((c) => (
          <div key={c.id} className="rounded border bg-white p-4 space-y-2">
            <div className="flex items-center justify-between">
              <p className="font-medium">
                {c.period} <StatusBadge status={c.status} />
              </p>
              {c.status === "draft" && isManagement && (
                <Button size="sm" onClick={() => approve.mutate(c.id)}>
                  Approve and adjust stock
                </Button>
              )}
            </div>
            {c.lines.filter((l) => l.variance !== 0).length === 0 ? (
              <p className="text-sm text-gray-500">No variances.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Item</TableHead>
                    <TableHead className="text-right">System</TableHead>
                    <TableHead className="text-right">Counted</TableHead>
                    <TableHead className="text-right">Difference</TableHead>
                    <TableHead>Reason</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {c.lines
                    .filter((l) => l.variance !== 0)
                    .map((l) => (
                      <TableRow key={l.item_id}>
                        <TableCell>
                          {itemMap.get(l.item_id)?.name} {itemMap.get(l.item_id)?.size}
                        </TableCell>
                        <TableCell className="text-right">{l.system_qty}</TableCell>
                        <TableCell className="text-right">{l.counted_qty}</TableCell>
                        <TableCell className={`text-right ${l.variance < 0 ? "text-red-600" : "text-green-700"}`}>{l.variance}</TableCell>
                        <TableCell>{l.reason ?? <span className="text-red-600">missing</span>}</TableCell>
                      </TableRow>
                    ))}
                </TableBody>
              </Table>
            )}
          </div>
        ))
      )}
      <Dialog open={counting} onOpenChange={setCounting}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Monthly count</DialogTitle>
          </DialogHeader>
          <Field label="Month">
            <Input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} />
          </Field>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Item</TableHead>
                <TableHead className="text-right">System</TableHead>
                <TableHead>Physical</TableHead>
                <TableHead>Reason (if different)</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {stock.map((s) => {
                const v = counted[s.item.id] ?? { qty: String(s.quantity), reason: "" };
                return (
                  <TableRow key={s.item.id}>
                    <TableCell className="text-sm">{itemLabel(s.item)}</TableCell>
                    <TableCell className="text-right">{s.quantity}</TableCell>
                    <TableCell>
                      <Input
                        type="number"
                        min={0}
                        className="w-20"
                        aria-label="Physical count"
                        value={v.qty}
                        onChange={(e) => setCounted({ ...counted, [s.item.id]: { ...v, qty: e.target.value } })}
                      />
                    </TableCell>
                    <TableCell>
                      {Number(v.qty) !== s.quantity && (
                        <Input value={v.reason} onChange={(e) => setCounted({ ...counted, [s.item.id]: { ...v, reason: e.target.value } })} />
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          <Button disabled={stock.length === 0 || save.isPending} onClick={() => save.mutate(undefined)}>
            Save count
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function Inventory() {
  return (
    <Page title="Inventory">
      <Tabs defaultValue="stock">
        <TabsList className="flex-wrap h-auto">
          <TabsTrigger value="stock">Stock & sales</TabsTrigger>
          <TabsTrigger value="purchasing">Purchase requests</TabsTrigger>
          <TabsTrigger value="transfers">Transfers</TabsTrigger>
          <TabsTrigger value="counts">Monthly counts</TabsTrigger>
        </TabsList>
        <TabsContent value="stock">
          <StockTab />
        </TabsContent>
        <TabsContent value="purchasing">
          <PurchasingTab />
        </TabsContent>
        <TabsContent value="transfers">
          <TransfersTab />
        </TabsContent>
        <TabsContent value="counts">
          <CountsTab />
        </TabsContent>
      </Tabs>
    </Page>
  );
}

