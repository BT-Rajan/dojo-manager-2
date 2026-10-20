import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/queryClient";
import type { Role, User } from "@/lib/types";

export function useAuth() {
  const { data: user, isLoading } = useQuery<User | null>({
    queryKey: ["/api/auth/me"],
    queryFn: async () => {
      try {
        return await api<User>("/api/auth/me");
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 5 * 60_000,
  });
  const role = user?.role;
  const is = (...roles: Role[]) => !!role && roles.includes(role);
  return {
    user: user ?? null,
    isLoading,
    isAuthenticated: !!user,
    isOwner: is("owner"),
    isManagement: is("owner", "manager"),
    isStaff: is("owner", "manager", "branch_admin"),
  };
}
