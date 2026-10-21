import { createContext, useContext } from "react";
import type { CoachProfile } from "@/lib/types";

/**
 * The coach whose portal is open. A coach always sees their own; staff pick a coach, and every
 * portal request then carries that coach's `instructor_id`.
 */
export interface CoachContextValue {
  coach: CoachProfile;
  /** Extra query params for /api/coach/... requests. */
  params: { instructor_id?: number };
  /** True when a coach is looking at their own portal (not staff viewing it). */
  isSelf: boolean;
}

export const CoachContext = createContext<CoachContextValue | null>(null);

export function useCoach(): CoachContextValue {
  const value = useContext(CoachContext);
  if (!value) throw new Error("useCoach outside CoachContext");
  return value;
}
