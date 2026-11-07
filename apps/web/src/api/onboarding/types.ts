export interface NteeCode {
  code: string;
  label: string;
  group: string;
  group_label: string;
}

export interface ProfileCitation {
  citation_id: string;
  kind: "profile";
  profile_path: string;
  quote: string;
}

export interface NteeSuggestion {
  code: string;
  label: string;
  reason: string;
  verified: boolean;
  citation: ProfileCitation | null;
}

export interface NteeSuggestionInput {
  mission_statement: string;
  programs: { name: string; description: string }[];
}

export interface NteeSuggestionResponse {
  suggestions: NteeSuggestion[];
  error: "suggestions_unavailable" | null;
}

export interface OnboardingApi {
  searchNtee(q: string, limit?: number): Promise<NteeCode[]>;
  suggestNtee(input: NteeSuggestionInput): Promise<NteeSuggestionResponse>;
}
