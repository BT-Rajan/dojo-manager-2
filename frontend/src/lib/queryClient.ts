import { QueryClient, QueryFunction } from "@tanstack/react-query";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

type Params = Record<string, string | number | boolean | null | undefined>;

export function buildUrl(url: string, params?: Params): string {
  if (!params) return url;
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
  }
  const s = qs.toString();
  return s ? `${url}?${s}` : url;
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    // FastAPI validation errors: [{loc: [...], msg}]
    if (Array.isArray(detail)) {
      return detail
        .map((d: { loc?: unknown[]; msg?: string }) => {
          const field = d.loc?.filter((p) => p !== "body").join(".");
          return field ? `${field}: ${d.msg}` : d.msg;
        })
        .join("; ");
    }
  } catch {
    /* not JSON */
  }
  return res.statusText || `Request failed (${res.status})`;
}

/** JSON API call. Sends the session cookie and the header the API requires on writes. */
export async function api<T = unknown>(
  url: string,
  options: { method?: string; body?: unknown; params?: Params } = {},
): Promise<T> {
  const { method = "GET", body, params } = options;
  const res = await fetch(buildUrl(url, params), {
    method,
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "X-Requested-With": "XMLHttpRequest",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res));
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Query keys are `[url, params?]`; switching branch changes params and refetches. */
const defaultQueryFn: QueryFunction = async ({ queryKey }) => {
  const [url, params] = queryKey as [string, Params | undefined];
  return api(url, { params });
};

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      queryFn: defaultQueryFn,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
      retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 2,
    },
    mutations: { retry: false },
  },
});
