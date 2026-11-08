import { API_URL, online } from "@/api/http";
import { FixtureOnboardingApi } from "./fixture";
import { HttpOnboardingApi } from "./http";
import type { OnboardingApi } from "./types";

export * from "./types";

export function onboardingApi(): OnboardingApi {
  return online ? new HttpOnboardingApi(API_URL) : new FixtureOnboardingApi("normal", 250);
}
