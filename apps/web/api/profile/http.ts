import { ProblemError, type FieldError, type ProfileApi, type ProfileForm, type ProfileSections, type ProfileView } from "./types";

type Body = Omit<ProfileView, "etag">;

async function problem(res: Response): Promise<ProblemError> {
  const body = (await res.json().catch(() => ({}))) as { code?: string; title?: string; detail?: string; errors?: FieldError[] };
  return new ProblemError(res.status, body.code ?? `http_${res.status}`, body.detail ?? body.title ?? res.statusText, body.errors ?? []);
}

export class HttpProfileApi implements ProfileApi {
  constructor(private readonly baseUrl: string) {}

  private async send(init: RequestInit = {}, etag?: string): Promise<Response> {
    const headers: Record<string, string> = init.body !== undefined ? { "Content-Type": "application/json" } : {};
    if (etag) headers["If-Match"] = etag;
    try {
      return await fetch(`${this.baseUrl}/v1/profile`, { ...init, credentials: "include", headers });
    } catch (err) {
      throw new ProblemError(0, "network_error", err instanceof Error ? err.message : "Network error");
    }
  }

  private async view(res: Response): Promise<ProfileView> {
    if (!res.ok) throw await problem(res);
    return { ...((await res.json()) as Body), etag: res.headers.get("ETag") ?? "" };
  }

  async getProfile(): Promise<ProfileView | null> {
    const res = await this.send();
    if (res.status === 404) return null;
    return this.view(res);
  }

  async saveProfile(form: ProfileForm, etag?: string): Promise<ProfileView> {
    return this.view(await this.send({ method: "PUT", body: JSON.stringify(form) }, etag));
  }

  async patchProfile(sections: ProfileSections, etag: string): Promise<ProfileView> {
    return this.view(await this.send({ method: "PATCH", body: JSON.stringify(sections) }, etag));
  }
}
