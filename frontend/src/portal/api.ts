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
  name_ar: string | null;
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
  first_name_ar: string | null;
  last_name_ar: string | null;
  branch_id: number;
  branch_name: string;
  branch_name_ar: string | null;
  branch_code: string;
  rank: { belt: BeltBrief; stripes: number; next_belt: BeltBrief | null } | null;
  next_class: { session_id: number; session_date: string; start_time: string; end_time: string; title: string; title_ar: string | null } | null;
  membership: { id: number; plan_name: string; start_date: string; end_date: string; status: string } | null;
  status: "active" | "expiring" | "expired" | "frozen" | "none";
  expiring: boolean;
}

export interface ClassRow {
  session_id: number;
  session_date: string;
  start_time: string;
  end_time: string;
  title: string;
  title_ar: string | null;
  regular: boolean;
  booking: { status: "booked" | "waitlisted" } | null;
  can_book: boolean;
}

export interface MemberDetail {
  member: {
    id: number;
    first_name: string;
    last_name: string;
    first_name_ar: string | null;
    last_name_ar: string | null;
    branch_name: string;
    branch_name_ar: string | null;
    branch_code: string;
  };
  status: FamilyMember["status"];
  membership: FamilyMember["membership"];
  classes: ClassRow[];
  attendance: { session_date: string; start_time: string; title: string; title_ar: string | null; status: string }[];
  renewal: { plan_name: string; price: string } | null;
  receipts: {
    reference: string;
    paid_at: string;
    amount: string;
    method: "knet" | "card" | "cash";
    lines: { description: string; amount: string }[];
  }[];
  freeze: { can_request: boolean; pending: boolean; used: boolean } | null;
  progress: Progress[];
  consent: { internal_records: boolean; social_media: boolean; website_marketing: boolean } | null;
  rules_signed: boolean;
  signer: string;
}

export interface ProgressBelt {
  id: number;
  name: string;
  name_ar: string | null;
  color: string;
  bjj_stripe: string | null;
  bjj_stripe_ar: string | null;
}

export interface Progress {
  belt: ProgressBelt;
  stripes: number;
  next: ProgressBelt | null;
  done: number;
  total: number;
  seminars: number;
  checks: { code: string; en: string; ar: string; have: number; need: number; ok: boolean }[];
  tests: { event_date: string; title: string }[];
  evaluations: { eval_date: string; instructor_name: string | null; notes: string | null }[];
  notes: { month: string; worked_on: string; next_steps: string }[];
}

export interface Renewal {
  reference: string;
  member_id: number;
  plan_name: string;
  amount: string;
  method: "knet" | "card";
  status: "pending" | "paid" | "failed";
  end_date: string | null;
  test_outcomes: { approve: string; decline: string } | null;
}

export interface Account {
  family: { id: number; first_name: string; last_name: string; first_name_ar: string | null; last_name_ar: string | null }[];
  email: string | null;
  mobile: string;
  service_on: boolean;
  broadcasts_on: boolean;
  recent: { at: string; text: string }[];
}
