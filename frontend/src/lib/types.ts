// Shapes returned by the FastAPI backend. Money values arrive as strings ("65.000").

export type Role = "owner" | "manager" | "branch_admin" | "instructor";

export interface Branch {
  id: number;
  name: string;
  code: string;
  address: string | null;
  phone: string | null;
  is_active: boolean;
}

export interface User {
  id: number;
  username: string;
  full_name: string;
  email: string | null;
  role: Role;
  is_active: boolean;
  last_login_at: string | null;
  branches: Branch[];
}

export interface Program {
  id: number;
  name: string;
  discipline: string;
  description: string | null;
  min_age: number | null;
  max_age: number | null;
  is_active: boolean;
}

export interface Belt {
  id: number;
  name: string;
  color: string;
  sort_order: number;
  phase: string;
  bjj_stripe: string | null;
  bjj_equivalent: string | null;
  seminars_required: number;
}

export interface Instructor {
  id: number;
  branch_id: number;
  user_id: number | null;
  full_name: string;
  phone: string | null;
  email: string | null;
  specialties: string | null;
  belt_rank_id: number | null;
  is_active: boolean;
}

export type MemberStatus = "active" | "frozen" | "inactive";
/** Derived from memberships: active = a membership covers today (Kuwait time). */
export type Standing = "active" | "lapsed" | "new" | "frozen" | "inactive";

export interface Member {
  id: number;
  branch_id: number;
  member_no: string | null;
  first_name: string;
  last_name: string;
  full_name: string;
  date_of_birth: string | null;
  age: number | null;
  gender: "male" | "female" | null;
  civil_id: string | null;
  phone: string;
  email: string | null;
  guardian_name: string | null;
  guardian_phone: string | null;
  emergency_contact_name: string | null;
  emergency_contact_phone: string | null;
  health_notes: string | null;
  media_consent: boolean;
  belt_rank_id: number | null;
  belt_rank: Belt | null;
  stripes: number;
  status: MemberStatus;
  standing: Standing;
  joined_on: string;
  notes: string | null;
}

export interface MemberBrief {
  id: number;
  member_no: string | null;
  first_name: string;
  last_name: string;
  phone: string;
  branch_id: number;
}

export interface Plan {
  id: number;
  name: string;
  branch_id: number | null;
  program_id: number | null;
  duration_days: number;
  price: string;
  is_active: boolean;
}

export interface Membership {
  id: number;
  member_id: number;
  branch_id: number;
  plan_id: number;
  plan: Plan;
  start_date: string;
  end_date: string;
  price: string;
  status: "active" | "frozen" | "cancelled";
  notes: string | null;
  days_left: number;
  is_expired: boolean;
  member?: MemberBrief;
}

export type PaymentMethod = "knet" | "card" | "cash";

export interface Payment {
  id: number;
  branch_id: number;
  member_id: number | null;
  membership_id: number | null;
  amount: string;
  method: PaymentMethod;
  category: string;
  reference: string | null;
  notes: string | null;
  paid_at: string;
  is_void: boolean;
  void_reason: string | null;
}

export interface Schedule {
  id: number;
  branch_id: number;
  program_id: number;
  instructor_id: number | null;
  title: string | null;
  weekday: number;
  start_time: string;
  end_time: string;
  capacity: number;
  room: string | null;
  is_active: boolean;
}

export interface ClassSession {
  id: number;
  branch_id: number;
  schedule_id: number | null;
  program_id: number;
  instructor_id: number | null;
  original_instructor_id: number | null;
  title: string | null;
  session_date: string;
  start_time: string;
  end_time: string;
  capacity: number;
  status: "scheduled" | "cancelled" | "completed";
  change_reason: string | null;
  members_notified_at: string | null;
  booked: number;
  attended: number;
}

export type AttendanceStatus = "booked" | "present" | "late" | "absent" | "excused" | "waitlisted" | "cancelled";

export interface AttendanceRow {
  /** null: a regular member with no booking or check-in for this class yet. */
  id: number | null;
  session_id: number;
  member_id: number;
  status: AttendanceStatus | null;
  checked_in_at: string | null;
  member: MemberBrief;
  has_active_membership: boolean;
  is_regular: boolean;
  source: "desk" | "portal";
  late_cancellation: boolean;
}

export interface Enrollment {
  id: number;
  member_id: number;
  schedule_id: number;
  start_date: string;
  end_date: string | null;
  weekday: number;
  start_time: string;
  end_time: string;
  program_id: number;
  title: string | null;
  is_active: boolean;
}

export interface Leave {
  id: number;
  instructor_id: number;
  branch_id: number;
  start_date: string;
  end_date: string;
  type: string;
  reason: string | null;
  cover_instructor_id: number | null;
}

export type LeadStatus =
  | "new"
  | "contacted"
  | "trial_booked"
  | "trial_attended"
  | "converted"
  | "lost";

export interface Lead {
  id: number;
  branch_id: number;
  full_name: string;
  phone: string;
  email: string | null;
  age: number | null;
  source: string;
  program_id: number | null;
  status: LeadStatus;
  owner_user_id: number | null;
  next_action: string | null;
  next_action_date: string | null;
  trial_session_id: number | null;
  converted_member_id: number | null;
  lost_reason: string | null;
  notes: string | null;
  created_at: string;
}

export interface GradingEvent {
  id: number;
  branch_id: number;
  title: string;
  event_date: string;
  examiner_instructor_id: number | null;
  status: "planned" | "completed" | "cancelled";
  notes: string | null;
}

export type GradingOutcome = "pending" | "pass" | "fail" | "deferred";

export interface GradingResult {
  id: number;
  event_id: number;
  member_id: number;
  from_rank_id: number | null;
  from_stripes: number;
  to_rank_id: number | null;
  to_stripes: number;
  outcome: GradingOutcome;
  notes: string | null;
}

export interface Eligibility {
  member_id: number;
  member_name: string;
  belt_rank_id: number | null;
  stripes: number;
  next_rank_id: number | null;
  seminar_points: number;
  seminars_required: number;
  classes_since_promotion: number;
  last_promoted_on: string | null;
  seminar_requirement_met: boolean;
}

export interface Seminar {
  id: number;
  branch_id: number;
  title: string;
  seminar_date: string;
  instructor_id: number | null;
  points: number;
  notes: string | null;
  attendee_count: number;
}

export interface FollowUp {
  id: number;
  member_id: number;
  method: string;
  outcome: string;
  next_action: string | null;
  notes: string | null;
  contacted_at: string;
}

export interface Incident {
  id: number;
  branch_id: number;
  ref_no: string | null;
  occurred_at: string;
  type: string;
  member_id: number | null;
  persons_involved: string | null;
  description: string;
  action_taken: string | null;
  guardian_informed: string | null;
  witnesses: string | null;
  reported_to_manager_at: string | null;
  status: "open" | "closed";
  closed_at: string | null;
}

export interface Complaint {
  id: number;
  branch_id: number;
  ref_no: string | null;
  received_on: string;
  contact_name: string;
  contact_phone: string | null;
  channel: string;
  description: string;
  escalated: boolean;
  outcome: string | null;
  member_informed_on: string | null;
  status: "open" | "closed";
  closed_on: string | null;
}

export interface Item {
  id: number;
  sku: string;
  name: string;
  category: string;
  size: string | null;
  unit_price: string;
  reorder_level: number;
  is_active: boolean;
}

export interface StockRow {
  branch_id: number;
  item: Item;
  quantity: number;
  below_reorder: boolean;
}

export interface Line {
  id?: number;
  item_id: number;
  quantity: number;
}

export interface PurchaseRequest {
  id: number;
  ref_no: string | null;
  branch_id: number;
  vendor_name: string;
  vendor_type: "local" | "international";
  status: "draft" | "submitted" | "approved" | "rejected" | "ordered" | "received";
  notes: string | null;
  submitted_at: string | null;
  decided_at: string | null;
  decision_note: string | null;
  lines: (Line & { unit_cost: string | null })[];
}

export interface Transfer {
  id: number;
  ref_no: string | null;
  from_branch_id: number;
  to_branch_id: number;
  status: "in_transit" | "received" | "cancelled";
  notes: string | null;
  sent_at: string;
  received_at: string | null;
  lines: Line[];
}

export interface StockCount {
  id: number;
  branch_id: number;
  period: string;
  status: "draft" | "approved";
  approved_at: string | null;
  lines: { item_id: number; system_qty: number; counted_qty: number; reason: string | null; variance: number }[];
}

export interface Dashboard {
  date: string;
  active_members: number;
  new_members_this_month: number;
  expiring_within_5_days: number;
  expired_last_30_days: number;
  today_classes: {
    id: number;
    branch_id: number;
    start_time: string;
    end_time: string;
    status: string;
    capacity: number;
    instructor_id: number | null;
    program: string;
    booked: number;
    attended: number;
  }[];
  open_leads: number;
  open_incidents: number;
  open_complaints: number;
  low_stock_items: number;
  revenue_today?: string;
  revenue_month?: string;
}

// ---------------------------------------------------------------- coach portal
/** The coach's part in a class: their own, someone else's they cover, or theirs being covered. */
export type CoachRole = "teaching" | "covering" | "covered";

export interface CoachSession extends ClassSession {
  coach_role: CoachRole | null;
}

export interface CoachProfile {
  id: number;
  branch_id: number;
  branch: Branch;
  user_id: number | null;
  full_name: string;
  phone: string | null;
  email: string | null;
  specialties: string | null;
  belt_rank_id: number | null;
  is_active: boolean;
  today: string;
  classes_today: number;
  classes_this_week: number;
  next_session: CoachSession | null;
  leave_today: Leave | null;
}

export interface CoachDay {
  date: string;
  sessions: CoachSession[];
  on_leave: Leave[];
}

export interface PortalAccess {
  instructor_id: number;
  full_name: string;
  branch_id: number;
  is_active: boolean;
  user_id: number | null;
  username: string | null;
  user_active: boolean | null;
  last_login_at: string | null;
}

// ---------------------------------------------------------------- member portal families
export interface GuardianLink {
  guardian_id: number;
  member_id: number;
  full_name: string;
  mobile: string;
  email: string | null;
  relationship: string;
  is_primary: boolean;
  other_member_ids: number[];
}
