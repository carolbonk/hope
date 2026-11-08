// One HTTP client for the hackathon API (`/v1`). Offline (no API URL) nothing here is called.
export const API_URL = process.env.NEXT_PUBLIC_HOPE_API_URL ?? "";
export const online = API_URL !== "";

export const UNAUTHORIZED_EVENT = "hope:unauthorized";

export type FieldError = { field: string; code: string; message: string };

export class ProblemError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly errors: FieldError[] = [],
  ) {
    super(message);
    this.name = "ProblemError";
  }
}

type ProblemBody = { code?: string; title?: string; detail?: string; errors?: FieldError[] };

/** `fetch(API_URL + path)` with the session cookie, JSON in and out. Errors are `ProblemError`s. */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let res: Response;
  try {
    res = await fetch(API_URL + path, { ...init, headers, credentials: "include" });
  } catch (err) {
    throw new ProblemError(0, "network_error", err instanceof Error ? err.message : "Network error");
  }
  if (res.status === 401 && typeof window !== "undefined") window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as ProblemBody;
    throw new ProblemError(res.status, body.code ?? `http_${res.status}`, body.detail ?? body.title ?? res.statusText, body.errors ?? []);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
