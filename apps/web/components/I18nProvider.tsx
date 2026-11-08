"use client";

import { createContext, useContext, useEffect, useSyncExternalStore } from "react";
import { dictionaries, type Dictionary } from "@/lib/i18n";
import { DEFAULT_LOCALE, LOCALE_COOKIE, parseLocale, type Locale } from "@/lib/locale";

type I18n = { locale: Locale; t: Dictionary; setLocale: (next: Locale) => void };

// The visitor's explicit choice (cookie) first, then the browser language. Read in the browser so pages stay static.
function detectLocale(): Locale {
  const cookie = document.cookie.split("; ").find((c) => c.startsWith(`${LOCALE_COOKIE}=`));
  const chosen = parseLocale(cookie?.slice(LOCALE_COOKIE.length + 1));
  if (chosen) return chosen;
  return /^es/i.test(navigator.language ?? "") ? "es" : DEFAULT_LOCALE;
}

const listeners = new Set<() => void>();
const subscribe = (fn: () => void) => {
  listeners.add(fn);
  return () => void listeners.delete(fn);
};

function setLocale(next: Locale) {
  document.cookie = `${LOCALE_COOKIE}=${next}; path=/; max-age=31536000; samesite=lax`;
  listeners.forEach((fn) => fn());
}

const I18nContext = createContext<I18n>({ locale: DEFAULT_LOCALE, t: dictionaries[DEFAULT_LOCALE], setLocale });

/** `locale` fixes the language (tests); without it the browser's choice is used after hydration. */
export function I18nProvider({ locale: fixed, children }: { locale?: Locale; children: React.ReactNode }) {
  const detected = useSyncExternalStore(subscribe, detectLocale, () => DEFAULT_LOCALE);
  const locale = fixed ?? detected;

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  return <I18nContext.Provider value={{ locale, t: dictionaries[locale], setLocale }}>{children}</I18nContext.Provider>;
}

export const useI18n = () => useContext(I18nContext);
