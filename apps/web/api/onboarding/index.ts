import { FixtureOnboardingApi } from "./fixture";
import { HttpOnboardingApi } from "./http";
import type { OnboardingApi } from "./types";

export * from "./types";

export function onboardingApi(): OnboardingApi {
  const url = process.env.NEXT_PUBLIC_HOPE_API_URL;
  return url ? new HttpOnboardingApi(url) : new FixtureOnboardingApi("normal", 250);
}
