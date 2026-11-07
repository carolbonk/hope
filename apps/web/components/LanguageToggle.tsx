"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { LOCALES, LOCALE_COOKIE, type Locale } from "@/lib/locale";
import { useI18n } from "./I18nProvider";

function saveLocale(next: Locale) {
  document.cookie = `${LOCALE_COOKIE}=${next}; path=/; max-age=31536000; samesite=lax`;
}

export function LanguageToggle({ tone = "dark" }: { tone?: "dark" | "light" }) {
  const { locale, t } = useI18n();
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  function choose(next: Locale) {
    if (next === locale) return;
    saveLocale(next);
    startTransition(() => router.refresh());
  }

  return (
    <div role="group" aria-label={t.languageLabel} className={`flex rounded-full border p-0.5 text-xs font-semibold ${tone === "dark" ? "border-gold/50" : "border-line glass-control"}`}>
      {LOCALES.map((l) => (
        <button
          key={l}
          type="button"
          onClick={() => choose(l)}
          disabled={pending}
          aria-pressed={l === locale}
          className={`rounded-full px-2.5 py-1 uppercase transition ${
            tone === "dark"
              ? l === locale
                ? "bg-gold text-navy"
                : "text-cream/80 hover:text-cream"
              : l === locale
                ? "bg-navy text-cream"
                : "text-navy/70 hover:text-navy"
          } focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-gold`}
        >
          {l}
        </button>
      ))}
    </div>
  );
}
