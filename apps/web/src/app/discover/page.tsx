import Link from "next/link";
import { Card, PageHeader } from "@/components/ui";

// Placeholder until H2 (SC24) replaces this route.
export default async function DiscoverPage({ searchParams }: { searchParams: Promise<{ onboarded?: string }> }) {
  const { onboarded } = await searchParams;
  return (
    <>
      <PageHeader title="Discover grants" description="Hope searches the web for grants that fit your profile." />
      <Card>
        {onboarded && (
          <p role="status" className="mb-3 font-semibold text-good">
            Profile saved. Let&rsquo;s find grants that fit.
          </p>
        )}
        <p className="text-sm text-ink-muted">The discovery agent is coming next.</p>
        <Link href="/onboarding?step=review" className="glass-focus mt-4 inline-block text-sm font-semibold text-accent-strong underline">
          Review your profile answers
        </Link>
      </Card>
    </>
  );
}
