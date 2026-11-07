import { ProblemError, type FieldError, type ProfileApi, type ProfileForm, type ProfileView } from "./types";

type Body = Omit<ProfileView, "etag">;

async function problem(res: Response): Promise<ProblemError> {
  const body = (await res.json().catch(() => ({}))) as { code?: string; title?: string; detail?: string; errors?: FieldError[] };
  return new ProblemError(res.status, body.code ?? `http_${res.status}`, body.detail ?? body.title ?? res.statusText, body.errors ?? []);
}

export class HttpProfileApi implements ProfileApi {
  constructor(private readonly baseUrl: string) {}

  async getProfile(): Promise<ProfileView | null> {
    const res = await fetch(`${this.baseUrl}/v1/profile`, { credentials: "include" });
    if (res.status === 404) return null;
    if (!res.ok) throw await problem(res);
    return { ...((await res.json()) as Body), etag: res.headers.get("ETag") ?? "" };
  }

  async saveProfile(form: ProfileForm, etag?: string): Promise<ProfileView> {
    const res = await fetch(`${this.baseUrl}/v1/profile`, {
      method: "PUT",
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(etag ? { "If-Match": etag } : {}) },
      body: JSON.stringify(form),
    });
    if (!res.ok) throw await problem(res);
    return { ...((await res.json()) as Body), etag: res.headers.get("ETag") ?? "" };
  }
}
