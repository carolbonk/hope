import type { Metadata } from "next";
import type { ReactNode } from "react";
import { I18nProvider } from "@/components/I18nProvider";
import { DEFAULT_LOCALE } from "@/lib/locale";
import "./globals.css";

export const metadata: Metadata = {
  title: "Hope",
  description: "Find funding that fits your nonprofit and prepare the application. Demo data.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang={DEFAULT_LOCALE}>
      <body className="min-h-screen">
        <I18nProvider>
          <main className="mx-auto max-w-6xl px-4 py-8 sm:py-10">{children}</main>
        </I18nProvider>
      </body>
    </html>
  );
}
