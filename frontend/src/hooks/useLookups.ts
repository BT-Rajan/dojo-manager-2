import { useQuery } from "@tanstack/react-query";
import type { Belt, Instructor, Item, Plan, Program } from "@/lib/types";

/** Reference data used across pages, cached and turned into id -> record maps. */
function byId<T extends { id: number }>(rows: T[] | undefined): Map<number, T> {
  return new Map((rows ?? []).map((r) => [r.id, r]));
}

export function usePrograms() {
  const q = useQuery<Program[]>({ queryKey: ["/api/programs"], staleTime: 5 * 60_000 });
  return { programs: q.data ?? [], programMap: byId(q.data) };
}

export function useBelts() {
  const q = useQuery<Belt[]>({ queryKey: ["/api/belts"], staleTime: 5 * 60_000 });
  return { belts: q.data ?? [], beltMap: byId(q.data) };
}

export function useInstructors(branchId: number | null) {
  const q = useQuery<Instructor[]>({
    queryKey: ["/api/instructors", { branch_id: branchId }],
    enabled: branchId !== null,
  });
  return { instructors: q.data ?? [], instructorMap: byId(q.data) };
}

export function usePlans(branchId: number | null) {
  const q = useQuery<Plan[]>({
    queryKey: ["/api/plans", { branch_id: branchId, active: true }],
    enabled: branchId !== null,
  });
  return { plans: q.data ?? [] };
}

export function useItems() {
  const q = useQuery<Item[]>({ queryKey: ["/api/inventory/items"], staleTime: 60_000 });
  return { items: q.data ?? [], itemMap: byId(q.data) };
}
