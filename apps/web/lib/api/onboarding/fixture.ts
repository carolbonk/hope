import { nteeLabel, searchNteeCodes } from "./ntee";
import type { NteeCode, NteeSuggestion, NteeSuggestionInput, NteeSuggestionResponse, OnboardingApi } from "./types";

export type OnboardingFixtureMode = "normal" | "unverified" | "down";

const RULES: { code: string; words: string[]; reason: string }[] = [
  { code: "E32", words: ["clinic", "dental", "preventive care"], reason: "Runs community clinics that deliver preventive and dental care." },
  { code: "F30", words: ["mental health"], reason: "Provides mental health support." },
  { code: "O50", words: ["youth", "mentor"], reason: "Runs programs for young people." },
  { code: "K31", words: ["food bank", "pantry", "meals"], reason: "Distributes food to families." },
  { code: "L41", words: ["homeless", "shelter"], reason: "Shelters people experiencing homelessness." },
];

/** Offline NTEE search and a keyword stand-in for H1's suggestion agent; quotes are exact substrings. */
export class FixtureOnboardingApi implements OnboardingApi {
  constructor(
    private readonly mode: OnboardingFixtureMode = "normal",
    private readonly delayMs = 0,
  ) {}

  private wait() {
    return new Promise((r) => setTimeout(r, this.delayMs));
  }

  async searchNtee(q: string, limit = 20): Promise<NteeCode[]> {
    await this.wait();
    return searchNteeCodes(q, limit);
  }

  async suggestNtee(input: NteeSuggestionInput): Promise<NteeSuggestionResponse> {
    await this.wait();
    if (this.mode === "down") return { suggestions: [], error: "suggestions_unavailable" };
    const sources = [
      { path: "mission.mission_statement", text: input.mission_statement },
      ...input.programs.map((p, i) => ({ path: `programs.${i}.description`, text: p.description })),
    ];
    const suggestions: NteeSuggestion[] = [];
    for (const rule of RULES) {
      for (const src of sources) {
        const lower = src.text.toLowerCase();
        const word = rule.words.find((w) => lower.includes(w));
        if (!word) continue;
        const at = lower.indexOf(word);
        suggestions.push({
          code: rule.code,
          label: nteeLabel(rule.code),
          reason: rule.reason,
          verified: this.mode !== "unverified",
          citation: {
            citation_id: `c${suggestions.length + 1}`,
            kind: "profile",
            profile_path: src.path,
            quote: src.text.slice(at, at + word.length),
          },
        });
        break;
      }
    }
    return { suggestions: suggestions.slice(0, 3), error: null };
  }
}
