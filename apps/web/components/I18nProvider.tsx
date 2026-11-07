"use client";

import { createContext, useContext } from "react";
import { dictionaries, type Dictionary } from "@/lib/i18n";
import type { Locale } from "@/lib/locale";

const I18nContext = createContext<{ locale: Locale; t: Dictionary }>({ locale: "en", t: dictionaries.en });

export function I18nProvider({ locale, children }: { locale: Locale; children: React.ReactNode }) {
  return <I18nContext.Provider value={{ locale, t: dictionaries[locale] }}>{children}</I18nContext.Provider>;
}

export const useI18n = () => useContext(I18nContext);
