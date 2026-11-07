import { ProblemError } from "@/api/profile/types";
import type { NteeCode, NteeSuggestionInput, NteeSuggestionResponse, OnboardingApi } from "./types";

export class HttpOnboardingApi implements OnboardingApi {
  constructor(private readonly baseUrl: string) {}

  async searchNtee(q: string, limit = 20): Promise<NteeCode[]> {
    const params = new URLSearchParams({ q, limit: String(limit) });
    const res = await fetch(`${this.baseUrl}/v1/profile/ntee-codes?${params}`, { credentials: "include" });
    if (!res.ok) throw new ProblemError(res.status, `http_${res.status}`, res.statusText);
    return ((await res.json()) as { items: NteeCode[] }).items;
  }

  async suggestNtee(input: NteeSuggestionInput): Promise<NteeSuggestionResponse> {
    const res = await fetch(`${this.baseUrl}/v1/profile/ntee-suggestions`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
    if (res.status === 429) throw new ProblemError(429, "rate_limited", "Too many requests. Try again in a minute.");
    if (!res.ok) throw new ProblemError(res.status, `http_${res.status}`, res.statusText);
    return (await res.json()) as NteeSuggestionResponse;
  }
}
