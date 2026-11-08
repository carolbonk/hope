"use client";

import { use } from "react";
import { BidWorkspace } from "@/components/hope/bids/BidWorkspace";
import { ClientOnly, Panel } from "@/components/hope/ui";
import { useBidsCopy } from "@/components/hope/bids/copy";
import { online } from "@/lib/api/http";

export default function BidPage({ params }: { params: Promise<{ oppId: string }> }) {
  const { oppId } = use(params);
  return (
    <ClientOnly>
      <Bid grantId={decodeURIComponent(oppId)} />
    </ClientOnly>
  );
}

function Bid({ grantId }: { grantId: string }) {
  const t = useBidsCopy().bids;
  if (!online)
    return (
      <Panel>
        <p data-testid="bids-offline">{t.offline}</p>
      </Panel>
    );
  return <BidWorkspace grantId={grantId} />;
}
