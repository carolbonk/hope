"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { ApiProvider } from "@/api/provider";
import { SessionProvider, useOptionalSession } from "@/api/session";
import { cx } from "@/lib/cx";

const NAV = [
  { href: "/matrix", label: "Opportunity Matrix" },
  { href: "/approvals", label: "Approval Inbox" },
  { href: "/workflows", label: "Workflows" },
  { href: "/profile", label: "Agency Profile" },
];

function UserChip() {
  const session = useOptionalSession();
  if (!session) return null;
  return (
    <div className="glass-chrome rounded-full px-4 py-1.5 text-sm">
      <span className="font-semibold">{session.display_name}</span>
      <span className="sr-only">, roles: {session.roles.join(", ")}</span>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <ApiProvider>
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 glass-panel rounded-xl px-4 py-2">
        Skip to content
      </a>
      <SessionProvider>
        <header className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 pt-6 sm:px-6">
          <Link href="/matrix" className="glass-focus glass-chrome flex items-center gap-2 rounded-2xl px-4 py-2">
            <span className="glass-inset flex size-8 items-center justify-center rounded-full font-bold text-accent-strong" aria-hidden="true">
              H
            </span>
            <span className="text-lg font-bold tracking-tight">Hope</span>
          </Link>
          <nav aria-label="Main" className="order-last w-full sm:order-none sm:w-auto">
            <ul className="glass-chrome flex flex-wrap gap-1 rounded-2xl p-1.5">
              {NAV.map((item) => {
                const active = pathname?.startsWith(item.href);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      className={cx(
                        "glass-focus block rounded-xl px-3 py-2 text-sm font-semibold motion-safe:transition-colors",
                        active ? "glass-active text-accent-strong" : "border border-transparent text-ink-muted hover:text-ink",
                      )}
                    >
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>
          <UserChip />
        </header>
        <main id="main" className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
          {children}
        </main>
      </SessionProvider>
    </ApiProvider>
  );
}
