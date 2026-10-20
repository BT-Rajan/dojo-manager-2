import { useSyncExternalStore } from "react";
import { useQuery } from "@tanstack/react-query";
import type { Branch } from "@/lib/types";

// Branch isolation on the client: every page reads the selected branch and includes its id
// in query keys and API params, so switching branch refetches everything. The server enforces
// the same rule independently.
const KEY = "selectedBranchId";
const listeners = new Set<() => void>();

function read(): number | null {
  try {
    const v = localStorage.getItem(KEY);
    return v ? Number(v) : null;
  } catch {
    return null;
  }
}

export function setSelectedBranch(id: number | null) {
  try {
    if (id === null) localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, String(id));
  } catch {
    /* storage unavailable */
  }
  listeners.forEach((l) => l());
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useBranches() {
  return useQuery<Branch[]>({ queryKey: ["/api/branches"] });
}

export function useBranch() {
  const branchId = useSyncExternalStore(subscribe, read, () => null);
  const { data: branches = [] } = useBranches();
  const branch = branches.find((b) => b.id === branchId) ?? null;
  return { branchId: branch ? branch.id : null, branch, branches };
}
