import type { Gate } from "@hope/schemas";
import { Badge, type IconName, type Tone } from "@/components/ui";
import type { CapacityFit, EligibilityStatus, Recommendation } from "@/api/types";
import { GATES } from "@/lib/gates";
import type { Urgency } from "@/lib/time";

type Spec = { tone: Tone; icon: IconName; label: string };

export const RECOMMENDATION: Record<Recommendation, Spec> = {
  pursue: { tone: "good", icon: "up", label: "Pursue" },
  consider: { tone: "info", icon: "scale", label: "Consider" },
  watch: { tone: "warn", icon: "eye", label: "Watch" },
  skip: { tone: "neutral", icon: "minus", label: "Skip" },
};

export const ELIGIBILITY: Record<EligibilityStatus, Spec> = {
  eligible: { tone: "good", icon: "check", label: "Eligible" },
  needs_review: { tone: "warn", icon: "alert", label: "Needs review" },
  ineligible: { tone: "bad", icon: "x", label: "Ineligible" },
};

export const CAPACITY: Record<CapacityFit, Spec> = {
  fits: { tone: "good", icon: "check", label: "Fits" },
  tight: { tone: "warn", icon: "alert", label: "Tight" },
  conflicts: { tone: "bad", icon: "x", label: "Conflicts" },
};

const URGENCY: Record<Urgency, { tone: Tone; icon: IconName }> = {
  overdue: { tone: "bad", icon: "alert" },
  urgent: { tone: "bad", icon: "clock" },
  soon: { tone: "warn", icon: "clock" },
  ok: { tone: "neutral", icon: "clock" },
};

const fromSpec = (s: Spec) => (
  <Badge tone={s.tone} icon={s.icon}>
    {s.label}
  </Badge>
);

export const RecommendationBadge = ({ value }: { value: Recommendation }) => fromSpec(RECOMMENDATION[value]);
export const EligibilityBadge = ({ value }: { value: EligibilityStatus }) => fromSpec(ELIGIBILITY[value]);
export const CapacityBadge = ({ value }: { value: CapacityFit | null | undefined }) =>
  value ? fromSpec(CAPACITY[value]) : <span className="text-ink-muted">—</span>;

export function UrgencyBadge({ urgency, label }: { urgency: Urgency; label: string }) {
  const s = URGENCY[urgency];
  return (
    <Badge tone={s.tone} icon={s.icon}>
      {label}
    </Badge>
  );
}

export function GateBadge({ gate }: { gate: Gate }) {
  return (
    <Badge tone="info" icon="shield">
      {gate} · {GATES[gate].title}
    </Badge>
  );
}

const ROLE_ACRONYMS: Record<string, string> = { aor: "AOR", cfo: "CFO" };
export const roleLabel = (role: string): string =>
  ROLE_ACRONYMS[role] ?? role.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
