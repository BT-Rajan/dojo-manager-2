/** Portal API calls. Errors carry the server's message (already in the family's language). */
export class PortalError extends Error {
  constructor(
    public status: number,
    message: string,
    public testMessage: string | null = null,
  ) {
    super(message);
  }
}

export async function portalApi<T = unknown>(url: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const { method = "GET", body } = options;
  const res = await fetch(url, {
    method,
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "X-Requested-With": "XMLHttpRequest",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let message = res.statusText || "Something went wrong";
    let test: string | null = null;
    try {
      const detail = (await res.json())?.detail;
      if (typeof detail === "string") message = detail;
      else if (detail && typeof detail === "object" && "message" in detail) {
        message = detail.message;
        test = detail.test_message ?? null;
      } else if (Array.isArray(detail)) message = detail.map((d: { msg?: string }) => d.msg).join("; ");
    } catch {
      /* not JSON */
    }
    throw new PortalError(res.status, message, test);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export interface PortalMe {
  kind: "guardian" | "member";
  name: string;
  mobile: string;
}

export interface BeltBrief {
  id: number;
  name: string;
  color: string;
}

export interface FamilyMember {
  id: number;
  first_name: string;
  last_name: string;
  branch_id: number;
  branch_name: string;
  branch_code: string;
  rank: { belt: BeltBrief; stripes: number; next_belt: BeltBrief | null } | null;
  next_class: { session_id: number; session_date: string; start_time: string; end_time: string; title: string } | null;
  membership: { id: number; plan_name: string; start_date: string; end_date: string; status: string } | null;
  status: "active" | "expiring" | "expired" | "frozen" | "none";
  expiring: boolean;
}
