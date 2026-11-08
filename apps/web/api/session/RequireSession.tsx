"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { online } from "@/api/http";
import { ErrorNotice, Loading } from "@/components/ui";
import { useHopeT } from "@/lib/hope/i18n";
import { useSession } from "./index";

/** SC00 session guard for `/hope/*`. Offline it renders the page and makes no request. */
export function RequireSession({ children }: { children: React.ReactNode }) {
  return online ? <OnlineGuard>{children}</OnlineGuard> : <>{children}</>;
}

function OnlineGuard({ children }: { children: React.ReactNode }) {
  const { status, me, retry } = useSession();
  const { h } = useHopeT();
  const router = useRouter();
  const path = usePathname();
  const notOnboarded = status === "ready" && !me?.onboarding_complete;

  useEffect(() => {
    if (status === "signed_out") router.replace(`/login?next=${encodeURIComponent(path + window.location.search)}`);
    else if (notOnboarded) router.replace("/onboarding");
  }, [status, notOnboarded, path, router]);

  if (status === "ready" && !notOnboarded) return <>{children}</>;
  if (status === "unreachable") {
    const [before, after] = h.session.unreachableBody.split("make demo");
    return (
      <ErrorNotice title={h.session.unreachableTitle} onRetry={retry}>
        {before}
        <code>make demo</code>
        {after}
      </ErrorNotice>
    );
  }
  return <Loading label={h.loading} />;
}
