"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ProblemError } from "@/lib/api/http";
import { invalidateSession, login, me, safeNext } from "@/lib/api/session";
import { LanguageToggle } from "@/components/LanguageToggle";
import { useI18n } from "@/components/I18nProvider";
import { Logo } from "@/components/hope/ui";
import { Button, Card, ErrorNotice, Loading, SuccessNotice, TextField } from "@/components/ui";
import { AutoDismiss } from "@/components/ui/AutoDismiss";
import { LOGIN_COPY, type LoginCopy } from "./copy";

type Field = "email" | "password";
type Errors = Partial<Record<Field, string>>;

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const FIELD_ORDER: Field[] = ["email", "password"];

function validate(v: Record<Field, string>, c: LoginCopy): Errors {
  const e: Errors = {};
  if (!v.email.trim()) e.email = c.emptyEmail;
  else if (!EMAIL_RE.test(v.email.trim())) e.email = c.badEmail;
  if (!v.password) e.password = c.emptyPassword;
  return e;
}

/** SC01 `/login`: sign-in only (accounts are created by an admin) against H0's session API. */
export function LoginScreen() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const { locale } = useI18n();
  const c = LOGIN_COPY[locale];
  const demo = process.env.NEXT_PUBLIC_HOPE_DEMO === "1";
  const next = params.get("next");
  const [signedOut] = useState(params.get("signedOut") === "1");
  const [checking, setChecking] = useState(true);
  const [values, setValues] = useState<Record<Field, string>>({ email: "", password: "" });
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [offline, setOffline] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const focus = (target: Field | "submit" | "formError") =>
    rootRef.current?.querySelector<HTMLElement>(`[data-focus="${target}"]`)?.focus();
  const focusAfter = useRef<Field | "submit" | "formError" | null>(null);

  const go = async () => {
    const who = await me();
    router.replace(who.onboarding_complete ? safeNext(next) : "/onboarding");
  };

  useEffect(() => {
    let live = true;
    me()
      .then((who) => {
        if (live) router.replace(who.onboarding_complete ? safeNext(next) : "/onboarding");
      })
      .catch(() => {
        if (live) setChecking(false);
      });
    return () => {
      live = false;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!signedOut) return;
    const rest = new URLSearchParams(params.toString());
    rest.delete("signedOut");
    const qs = rest.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname);
  }, [signedOut]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const sync = () => setOffline(!navigator.onLine);
    sync();
    window.addEventListener("online", sync);
    window.addEventListener("offline", sync);
    return () => {
      window.removeEventListener("online", sync);
      window.removeEventListener("offline", sync);
    };
  }, []);

  useEffect(() => {
    if (checking) return;
    focus("email");
  }, [checking]);

  useEffect(() => {
    if (!focusAfter.current) return;
    focus(focusAfter.current);
    focusAfter.current = null;
  });

  const set = (field: Field) => (e: React.ChangeEvent<HTMLInputElement>) => setValues((v) => ({ ...v, [field]: e.target.value }));

  const fail = (err: unknown) => {
    const p = err instanceof ProblemError ? err : null;
    if (p?.code === "invalid_credentials") {
      setValues((v) => ({ ...v, password: "" }));
      setFormError(c.invalidCredentials);
      focusAfter.current = "password";
    } else if (p?.status === 422 && p.errors.length) {
      const map: Errors = {};
      for (const fe of p.errors) if (FIELD_ORDER.includes(fe.field as Field)) map[fe.field as Field] = fe.message;
      setErrors(map);
      focusAfter.current = FIELD_ORDER.find((f) => map[f]) ?? "formError";
    } else if (p?.status === 429) {
      setFormError(c.rateLimited);
      focusAfter.current = "formError";
    } else {
      setFormError(c.network);
      focusAfter.current = "formError";
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy || offline) return;
    setFormError(null);
    const errs = validate(values, c);
    setErrors(errs);
    const first = FIELD_ORDER.find((f) => errs[f]);
    if (first) {
      focusAfter.current = first;
      return;
    }
    setBusy(true);
    const email = values.email.trim().toLowerCase();
    try {
      await login({ email, password: values.password });
      invalidateSession();
      await go();
    } catch (err) {
      fail(err);
      setBusy(false);
    }
  };

  const useDemo = () => {
    setValues((v) => ({ ...v, email: "demo@hope.org", password: "hope-demo" }));
    setErrors({});
    setFormError(null);
    focusAfter.current = "submit";
  };

  return (
    <div ref={rootRef} className="mx-auto w-full max-w-[440px] pt-6 sm:pt-0">
      <Card className="space-y-5">
        <div className="flex items-center justify-between gap-3">
          <Logo />
          <LanguageToggle tone="light" />
        </div>
        <h1 className="sr-only">{c.headingSignin}</h1>
        <p className="text-sm text-ink-muted">{c.promise}</p>
        {signedOut && <SuccessNotice>{c.signedOut}</SuccessNotice>}
        {checking ? (
          <Loading label={c.checking} />
        ) : (
          <>
            <form noValidate onSubmit={submit} className="space-y-4">
              <TextField
                data-focus="email"
                label={c.email}
                type="email"
                autoComplete="email"
                required
                value={values.email}
                onChange={set("email")}
                readOnly={busy}
                error={errors.email}
              />
              <div className="flex items-end gap-2">
                <TextField
                  data-focus="password"
                  wrapperClassName="flex-1"
                  label={c.password}
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  value={values.password}
                  onChange={set("password")}
                  readOnly={busy}
                  error={errors.password}
                />
                <Button variant="ghost" pressed={showPassword} onClick={() => setShowPassword((s) => !s)}>
                  {showPassword ? c.hide : c.show}
                </Button>
              </div>
              {formError && (
                <div
                  tabIndex={-1}
                  data-focus="formError"
                >
                  <AutoDismiss key={formError} onDismiss={() => setFormError(null)}>
                    <ErrorNotice title={c.errorTitle}>{formError}</ErrorNotice>
                  </AutoDismiss>
                </div>
              )}
              {offline && <p className="text-sm text-bad">{c.offline}</p>}
              <Button
                data-focus="submit"
                type="submit"
                variant="primary"
                className="min-h-12 w-full"
                disabled={busy || offline}
              >
                {busy ? c.signingIn : c.submitSignin}
              </Button>
            </form>
            <p className="text-sm text-ink-muted">{c.noAccount}</p>
            {demo && (
              <div className="space-y-2 border-t border-white/20 pt-4 text-sm">
                <p>{c.demoHint}</p>
                <Button variant="ghost" onClick={useDemo}>
                  {c.useDemo}
                </Button>
              </div>
            )}
          </>
        )}
        <p className="text-xs text-ink-muted">{c.free}</p>
      </Card>
    </div>
  );
}
