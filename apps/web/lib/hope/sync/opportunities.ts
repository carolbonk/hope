import type { Opportunity } from "../types";

// H2 replaces this body. Contract: never reject; `null` = use the demo catalog (or sync off).
// Money on the wire is {amount_minor, currency}; convert here (amount_minor / 100), never in pages.
export function fetchOpportunities(): Promise<Opportunity[] | null> {
  return Promise.resolve(null);
}
