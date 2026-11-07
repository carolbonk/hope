import type { Metadata } from "next";
import type { ReactNode } from "react";
import { I18nProvider } from "@/components/I18nProvider";
import { getLocale } from "@/lib/i18n/server";
import "./globals.css";

export const metadata: Metadata = {
  title: "Hope",
  description: "Find funding that fits your nonprofit and prepare the application. Demo data.",
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  const locale = await getLocale();
  return (
    <html lang={locale}>
      <body className="min-h-screen">
        <I18nProvider locale={locale}>
          <main className="mx-auto max-w-6xl px-4 py-8 sm:py-10">{children}</main>
        </I18nProvider>
      </body>
    </html>
  );
}
