import { useQuery } from "@tanstack/react-query";
import { Empty, Loading, StatusBadge } from "@/components/common";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useApiMutation } from "@/hooks/useApiMutation";
import { fmtDateTime, label } from "@/lib/format";
import { api } from "@/lib/queryClient";
import type { FamilyMessage, Member, MessageChoices } from "@/lib/types";

/** WhatsApp messages to the member's family, and what the family chose to receive. */
export function MessagesTab({ member }: { member: Member }) {
  const url = `/api/members/${member.id}/messages`;
  const choicesUrl = `/api/members/${member.id}/message-choices`;
  const { data: rows = [], isLoading } = useQuery<FamilyMessage[]>({ queryKey: [url] });
  const { data: choices } = useQuery<MessageChoices>({ queryKey: [choicesUrl] });
  const set = useApiMutation((body: Partial<Pick<MessageChoices, "service_on" | "broadcasts_on">>) => api(choicesUrl, { method: "POST", body }), {
    invalidate: [choicesUrl],
    success: "Message choices saved",
  });

  return (
    <div className="space-y-4">
      {choices && (
        <div className="rounded border p-3 space-y-2 text-sm">
          <p className="text-muted-foreground">
            Messages go to <span className="tabular">{choices.mobile ?? "no Kuwait mobile on record"}</span>. Receipts, sign-in codes, trial and
            class-change messages are always sent.
          </p>
          <label className="flex items-center justify-between gap-2">
            Reminders, test days and progress notes
            <Switch checked={choices.service_on} disabled={!choices.mobile} onCheckedChange={(c) => set.mutate({ service_on: c })} />
          </label>
          <label className="flex items-center justify-between gap-2">
            News and offers from the academy
            <Switch checked={choices.broadcasts_on} onCheckedChange={(c) => set.mutate({ broadcasts_on: c })} />
          </label>
          {choices.history.length > 0 && (
            <p className="text-xs text-muted-foreground">
              News and offers last set {choices.history[0].opted_in ? "on" : "off"} in the {choices.history[0].source === "portal" ? "member portal" : "front desk"}{" "}
              on {fmtDateTime(choices.history[0].at)}.
            </p>
          )}
        </div>
      )}
      {isLoading ? (
        <Loading />
      ) : rows.length === 0 ? (
        <Empty>No messages sent to this family yet.</Empty>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>When</TableHead>
              <TableHead>Message</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((m) => (
              <TableRow key={m.id}>
                <TableCell className="whitespace-nowrap text-xs">{fmtDateTime(m.at)}</TableCell>
                <TableCell className="max-w-md text-sm" dir="auto">
                  {m.text}
                </TableCell>
                <TableCell className="text-xs">
                  {label(m.kind || m.category)}
                  <p className="text-muted-foreground">{label(m.category)}</p>
                </TableCell>
                <TableCell>
                  <StatusBadge status={m.status} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
