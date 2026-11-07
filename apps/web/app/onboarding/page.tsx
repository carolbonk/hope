import { Suspense } from "react";
import { OnboardingWizard } from "@/features/onboarding/OnboardingWizard";

export const metadata = { title: "Set up your profile · Hope" };

export default function OnboardingPage() {
  return (
    <Suspense>
      <OnboardingWizard />
    </Suspense>
  );
}
