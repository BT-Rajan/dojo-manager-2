import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useToast } from "@/hooks/use-toast";

/**
 * Wraps a mutation with error toasts and cache invalidation. `invalidate` lists URL prefixes;
 * every cached query whose key starts with one of them is refetched.
 */
export function useApiMutation<TVars, TResult = unknown>(
  fn: (vars: TVars) => Promise<TResult>,
  opts: { invalidate?: string[]; success?: string; onSuccess?: (r: TResult) => void } = {},
) {
  const qc = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: fn,
    onSuccess: (result) => {
      for (const prefix of opts.invalidate ?? []) {
        qc.invalidateQueries({
          predicate: (q) => typeof q.queryKey[0] === "string" && q.queryKey[0].startsWith(prefix),
        });
      }
      if (opts.success) toast({ title: opts.success });
      opts.onSuccess?.(result);
    },
    onError: (e: Error) => toast({ title: "Something went wrong", description: e.message, variant: "destructive" }),
  });
}
