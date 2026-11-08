"use client";

import { seedHopeProfile } from "@/lib/hope/fromOnboarding";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { onboardingApi as defaultOnboardingApi, type OnboardingApi } from "@/api/onboarding";
import { profileApi as defaultProfileApi, ProblemError, type ProfileApi, type ProfileForm } from "@/api/profile";
import { Button, Card, ErrorNotice, SuccessNotice } from "@/components/ui";
import { cx } from "@/lib/cx";
import { clearDraft, loadDraft, saveDraft } from "./useOnboardingDraft";
import { emptyForm, fieldErrorsToMap, firstIncomplete, isStepId, stepIndex, stepOfField, STEPS, validateStep, type Errors, type StepId } from "./model";
import { BasicsStep } from "./steps/BasicsStep";
import { BudgetStep } from "./steps/BudgetStep";
import { CauseStep } from "./steps/CauseStep";
import { MissionStep } from "./steps/MissionStep";
import { ProgramsStep } from "./steps/ProgramsStep";
import { ReviewStep } from "./steps/ReviewStep";
import { AutoDismiss } from "@/components/ui/AutoDismiss";

export const AFTER_ONBOARDING = "/hope/discover?onboarded=1";

type SaveProblem = { kind: "conflict" } | { kind: "failed" } | null;

export function OnboardingWizard({ profile, onboarding }: { profile?: ProfileApi; onboarding?: OnboardingApi }) {
  const profileApi = useMemo(() => profile ?? defaultProfileApi(), [profile]);
  const ntee = useMemo(() => onboarding ?? defaultOnboardingApi(), [onboarding]);
  const router = useRouter();
  const pathname = usePathname() ?? "/onboarding";
  const params = useSearchParams();

  const [form, setForm] = useState<ProfileForm | null>(null);
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [etag, setEtag] = useState<string | undefined>();
  const [startStep, setStartStep] = useState<StepId>("basics");
  const [restored, setRestored] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [saving, setSaving] = useState(false);
  const [saveProblem, setSaveProblem] = useState<SaveProblem>(null);
  const [offline, setOffline] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const body = useRef<HTMLDivElement>(null);
  const focusInvalid = useRef(false);
  const firstRender = useRef(true);

  const load = useCallback(async () => {
    try {
      const existing = await profileApi.getProfile();
      if (existing) {
        setForm(existing.form);
        setStartStep(firstIncomplete(existing.form));
        setLabels(existing.ntee_labels);
        setEtag(existing.etag);
        return existing;
      }
      const draft = loadDraft();
      const initial = draft ?? emptyForm();
      setForm(initial);
      setStartStep(firstIncomplete(initial));
      setRestored(!!draft);
      return null;
    } catch {
      setLoadError(true);
      return null;
    }
  }, [profileApi]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial fetch; state is set after the await
    void load();
  }, [load]);

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

  const requested = params.get("step");
  const step: StepId = useMemo(() => {
    if (!form || !isStepId(requested)) return startStep;
    return stepIndex(requested) <= stepIndex(firstIncomplete(form)) ? requested : startStep;
  }, [form, requested, startStep]);
  const index = stepIndex(step);
  const meta = STEPS[index]!;

  useEffect(() => {
    if (!form) return;
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    heading.current?.focus();
  }, [step, form === null]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!focusInvalid.current) return;
    focusInvalid.current = false;
    body.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
  });

  const set = useCallback((update: (f: ProfileForm) => ProfileForm) => setForm((f) => (f ? update(f) : f)), []);

  const go = (target: StepId) => {
    setSaveProblem(null);
    router.push(`${pathname}?step=${target}`);
  };

  const next = () => {
    if (!form) return;
    const errs = validateStep(step, form);
    setErrors(errs);
    if (Object.keys(errs).length) {
      focusInvalid.current = true;
      return;
    }
    saveDraft(form);
    go(STEPS[index + 1]!.id);
  };

  const back = () => {
    setErrors({});
    if (index > 0) go(STEPS[index - 1]!.id);
  };

  const finish = async (retried = false) => {
    if (!form) return;
    setSaving(true);
    setSaveProblem(null);
    try {
      await profileApi.saveProfile(form, etag);
      seedHopeProfile(form);
      clearDraft();
      router.replace(AFTER_ONBOARDING);
    } catch (err) {
      if (err instanceof ProblemError && err.status === 422) {
        const map = fieldErrorsToMap(err.errors);
        setErrors(map);
        const steps = err.errors.map((e) => stepOfField(e.field));
        const first = STEPS.find((s) => steps.includes(s.id));
        if (first && first.id !== "review") {
          focusInvalid.current = true;
          go(first.id);
        }
      } else if (err instanceof ProblemError && err.status === 428 && !retried) {
        const fresh = await profileApi.getProfile().catch(() => null);
        if (fresh) {
          setEtag(fresh.etag);
          setSaving(false);
          return finish(true);
        }
        setSaveProblem({ kind: "failed" });
      } else if (err instanceof ProblemError && err.status === 409) setSaveProblem({ kind: "conflict" });
      else if (err instanceof ProblemError && err.status === 401) router.replace(`/login?returnTo=${encodeURIComponent("/onboarding")}`);
      else setSaveProblem({ kind: "failed" });
    } finally {
      setSaving(false);
    }
  };

  const loadTheirs = async () => {
    setSaveProblem(null);
    setErrors({});
    await load();
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (step === "review") void finish();
    else next();
  };

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && (e.target as HTMLElement).tagName === "TEXTAREA") {
      e.preventDefault();
      onSubmit(e);
    }
  };

  if (loadError)
    return (
      <div className="mx-auto max-w-xl">
        <ErrorNotice title="We couldn't load your profile." onRetry={() => {
            setLoadError(false);
            void load();
          }}>
          Check your connection and try again.
        </ErrorNotice>
      </div>
    );

  if (!form)
    return (
      <div role="status" aria-label="Loading your profile" className="grid gap-6 lg:grid-cols-[260px_1fr]">
        <div className="glass-inset hidden h-80 animate-pulse rounded-2xl lg:block" />
        <div className="glass-panel flex h-80 flex-col gap-4 rounded-[var(--radius-glass)] p-6">
          {[0, 1, 2].map((i) => (
            <div key={i} className="glass-inset h-12 animate-pulse rounded-xl" />
          ))}
        </div>
      </div>
    );

  const pct = Math.round((index / (STEPS.length - 1)) * 100);
  const reachable = stepIndex(firstIncomplete(form));
  const reviewErrors = step === "review" ? errors : {};

  return (
    <div className="grid gap-6 pb-24 sm:pb-0 lg:grid-cols-[260px_minmax(0,720px)] lg:justify-center">
      <p className="sr-only" aria-live="polite">
        Step {index + 1} of {STEPS.length}, {meta.title}
      </p>

      <aside aria-label="Setup progress" className="glass-inset hidden self-start rounded-2xl p-5 lg:block">
        <p className="text-sm font-semibold text-ink">Set up your profile</p>
        <Progress pct={pct} />
        <ol className="mt-4 flex flex-col gap-1">
          {STEPS.map((s, i) => {
            const done = i < index && i < reachable + 1;
            const enabled = i <= Math.max(reachable, index);
            return (
              <li key={s.id}>
                <button
                  type="button"
                  disabled={!enabled || saving}
                  aria-current={i === index ? "step" : undefined}
                  onClick={() => go(s.id)}
                  className={cx(
                    "glass-focus flex w-full items-center gap-2 rounded-xl border px-3 py-2 text-left text-sm",
                    i === index ? "glass-active font-semibold text-accent-strong" : "border-transparent text-ink-muted hover:text-ink disabled:opacity-50",
                  )}
                >
                  <span aria-hidden="true" className="w-4 text-center">
                    {done ? "✓" : i === index ? "●" : "○"}
                  </span>
                  {i + 1} {s.rail}
                  {done && <span className="sr-only">, completed</span>}
                </button>
              </li>
            );
          })}
        </ol>
      </aside>

      <div className="flex flex-col gap-4">
        <div className="glass-chrome rounded-2xl px-4 py-3 lg:hidden">
          <p className="text-sm font-semibold text-ink">
            Step {index + 1} of {STEPS.length} · {meta.title}
          </p>
          <Progress pct={pct} />
        </div>

        {offline && (
          <AutoDismiss>
            <div role="status" className="glass-chrome rounded-2xl border-l-4 border-warn px-4 py-3 text-sm text-ink">
              You&rsquo;re offline. Your answers are saved on this device.
            </div>
          </AutoDismiss>
        )}
        {restored && step === startStep && <SuccessNotice>We restored your progress.</SuccessNotice>}

        <Card>
          <form noValidate onSubmit={onSubmit} onKeyDown={onKeyDown} aria-labelledby="onboarding-step-title">
            <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
              Step {index + 1} of {STEPS.length}
            </p>
            <h1 id="onboarding-step-title" ref={heading} tabIndex={-1} className="mt-1 text-2xl font-semibold tracking-tight text-ink focus:outline-none">
              {meta.title}
            </h1>
            <p className="mt-1 text-sm text-ink-muted">{meta.why}</p>

            <div ref={body} className="mt-6">
              {step === "basics" && <BasicsStep form={form} set={set} errors={errors} />}
              {step === "mission" && <MissionStep form={form} set={set} errors={errors} />}
              {step === "cause" && <CauseStep form={form} set={set} errors={errors} api={ntee} labels={labels} setLabels={setLabels} />}
              {step === "budget" && <BudgetStep form={form} set={set} errors={errors} />}
              {step === "programs" && <ProgramsStep form={form} set={set} errors={errors} />}
              {step === "review" && <ReviewStep form={form} set={set} errors={reviewErrors} labels={labels} onEdit={go} saving={saving} />}
            </div>

            {saveProblem?.kind === "conflict" && (
              <AutoDismiss>
                <div role="alert" className="glass-inset mt-4 flex flex-wrap items-center gap-3 rounded-2xl border-l-4 border-warn p-4 text-sm">
                  <p className="flex-1">Someone else saved the profile while you were editing.</p>
                  <Button onClick={() => void loadTheirs()}>Load their version</Button>
                </div>
              </AutoDismiss>
            )}
            {saveProblem?.kind === "failed" && (
              <AutoDismiss>
                <div role="alert" className="glass-inset mt-4 flex flex-wrap items-center gap-3 rounded-2xl border-l-4 border-bad p-4 text-sm">
                  <p className="flex-1">We couldn&rsquo;t save your profile. Your answers are kept on this device. Try again.</p>
                  <Button onClick={() => void finish()}>Retry</Button>
                </div>
              </AutoDismiss>
            )}

            <div className="glass-chrome fixed inset-x-0 bottom-0 z-30 flex justify-end gap-3 rounded-none px-4 py-3 sm:static sm:mt-6 sm:border-0 sm:bg-transparent sm:p-0 sm:shadow-none sm:backdrop-blur-none">
              {index > 0 && (
                <Button onClick={back} disabled={saving}>
                  ← Back
                </Button>
              )}
              {step === "review" ? (
                <Button type="submit" variant="primary" disabled={saving || offline}>
                  {saving ? "Saving…" : "Finish and find grants"}
                </Button>
              ) : (
                <Button type="submit" variant="primary">
                  Continue →
                </Button>
              )}
            </div>
          </form>
        </Card>
      </div>
    </div>
  );
}

function Progress({ pct }: { pct: number }) {
  return (
    <div role="progressbar" aria-label="Setup progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} className="glass-inset mt-2 h-2 overflow-hidden rounded-full">
      <div className="h-full rounded-full bg-accent motion-safe:transition-[width] motion-safe:duration-300" style={{ width: `${Math.max(pct, 4)}%` }} />
    </div>
  );
}
