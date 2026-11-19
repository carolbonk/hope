import type { ReactNode } from "react";
import { demoOpportunities } from "@/lib/hope/demo";

// The static demo build prerenders the demo grants; other ids render on request.
export function generateStaticParams() {
  return demoOpportunities(new Date()).map((o) => ({ oppId: o.id }));
}

export default function Layout({ children }: { children: ReactNode }) {
  return children;
}
