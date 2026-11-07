import "server-only";
import { cookies, headers } from "next/headers";
import { DEFAULT_LOCALE, LOCALE_COOKIE, parseLocale, type Locale } from "../locale";

// The visitor's explicit choice (cookie) first, then the browser language.
export async function getLocale(): Promise<Locale> {
  const chosen = parseLocale((await cookies()).get(LOCALE_COOKIE)?.value);
  if (chosen) return chosen;
  const accept = (await headers()).get("accept-language") ?? "";
  if (/^es/i.test(accept)) return "es";
  return DEFAULT_LOCALE;
}
