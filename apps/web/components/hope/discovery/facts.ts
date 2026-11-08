import { useCheckCopy } from "@/app/hope/discover/copy";
import { daysUntil, money } from "@/components/hope/ui";
import { useToday } from "@/components/useToday";
import { useHopeT } from "@/lib/hope/i18n";
import { isRolling } from "@/lib/hope/sync/opportunities";
import type { Opportunity } from "@/lib/hope/types";

/** Amount and deadline wording for any grant: an unknown shows as not found (or rolling), never $0 or a guessed date. */
export function useGrantFacts() {
  const { h, locale } = useHopeT();
  const c = useCheckCopy();
  const today = useToday()!;
  const days = (o: Opportunity) => (o.deadline ? daysUntil(o.deadline, today) : null);
  return {
    days,
    amount: (o: Opportunity, range = true) =>
      o.amountMax === null
        ? o.otherCurrency
          ? c.currency(o.otherCurrency)
          : c.amountUnknown
        : range && o.amountMin !== null && o.amountMin !== o.amountMax
          ? `${money(o.amountMin, o.currency, locale)}–${money(o.amountMax, o.currency, locale)}`
          : money(o.amountMax, o.currency, locale),
    due: (o: Opportunity) => (o.deadline ? h.discover.due(o.deadline, days(o)!) : isRolling(o) ? c.rolling : c.deadlineUnknown),
  };
}

/** Sort key helpers that put unknowns last. */
export const byDeadline = (x: Opportunity, y: Opportunity) => (x.deadline === null ? 1 : 0) - (y.deadline === null ? 1 : 0) || (x.deadline ?? "").localeCompare(y.deadline ?? "");
