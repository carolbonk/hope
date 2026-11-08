# SC29: Application workspace: the funder's own form, translated

| | |
|---|---|
| Route | `/hope/applications/[oppId]` (stages `drafting`, `ready`). Replaces SC28's fixed 6-section panel once built |
| Files | `apps/web/app/hope/applications/[oppId]/page.tsx` (stage gate stays as SC27), new `apps/web/components/hope/apply/*` (`FormSource`, `TermsPanel`, `TermRow`, `QuestionList`, `AnswerEditor`, `TodoPanel`, `ReadyPanel`, `SourceDrawer`), `apps/web/lib/hope/sync/applications.ts` |
| Backend | H6 ([`H6-application-help.md`](../features/H6-application-help.md)), `/v1/applications/*` |
| Primary users | The grants lead or executive director of a small nonprofit, often a volunteer, plus the person who owns finance |
| Can act | Signed-in members of the nonprofit |
| Status | Spec for the team to review. Backend built; UI not built |

## 1. Purpose and user goals

Every funder asks for the same things in different words and buries them in jargon (UEI, SF-424A, NICRA,
"Organizational Capacity", "Statement of Need"). The screen turns one funder's form into a guided list the
team can finish in hours. Within 10 seconds a first-time user can tell:
1. **What is this funder asking for?** Each question in the funder's exact words, with its limit.
2. **What does it mean?** Plain English for every confusing term, with the source of the explanation.
3. **What do we still owe, and who?** A to-do list by owner (program, finance, director), long lead times first.
4. **Is it ready?** Every question drafted and in its limit, every upload matched, nothing left to confirm.

**Primary action:** "Draft all answers". **Secondary actions:** paste or upload the form, redraft one answer,
edit an answer, answer a to-do once, open a source, export, mark ready.

Never: submit to the funder, log into the funder's portal, or show a plain-language meaning without saying
where it came from.

## 2. Layout (desktop; below `lg` the right column moves under the left)

```text
[ Workspace header + StageBar (SC27) ]
┌ Funder's form ─────────────────────────────────────────────────────────────┐
│ Read from 3 funder pages · Revision 2 · 6 questions · 4 uploads              │
│ Questions behind a login? [Paste the form] [Upload the PDF]   [Read again]  │
└──────────────────────────────────────────────────────────────────────────────┘
┌ What the funder is asking (left, 2/3) ────────┐ ┌ To do (right, 1/3) ─────────┐
│ ▸ Words to know (5)              [Show all 12] │ │ At risk (1)                 │
│   SAM.gov registration · Action needed · Dir.  │ │ ⚠ SAM.gov: renew (~10 days, │
│   "Applicants must have an active SAM.gov…" ↗  │ │   9 left) · Director        │
│   = The federal government's list of orgs…     │ │ Finance (2)                 │
│   Source: SAM.gov (official) ↗                 │ │ ○ Budget: indirect rate     │
│ ▾ 1. Community Problem (250 words)  Drafted    │ │ Program (3)                 │
│   "Why is this work urgent in your community?" │ │ ○ Timeline and milestones   │
│   [answer textarea .....................] 212/250 words · AI draft        │ │   [answer once ......] Save │
│   ⚠ 1 thing to confirm: local data on need    │ │ ✓ 501(c)(3) letter: on file │
│   [Redraft]  Sources (3)                       │ │                             │
│ ▸ 2. Organization Snapshot (1,500 chars) Missing│ └─────────────────────────────┘
│ Uploads: IRS letter ✓ on file · Board list ○  │
└────────────────────────────────────────────────┘
┌ Ready to submit ──────────────────────────────────────────────────────────────┐
│ 5 of 6 answers done · 1 over limit · 2 to confirm · deadline Feb 15 (99 days) │
│ [Download for the portal (.md)]  [Copy all]              [Mark ready]          │
│ Hope never submits. A person submits through the funder's portal.             │
└────────────────────────────────────────────────────────────────────────────────┘
[ SourceDrawer (Modal variant="drawer"): funder quote + page link, profile facts used ]
```

## 3. Data and endpoints

All reads come from `GET /v1/applications/{id}` (`ApplicationView`). Writes return the new view; send
`If-Match: <version>` and on `412` reload and show "Someone else changed this application. We loaded the
latest version."

| Panel | Field / call | Notes |
|---|---|---|
| Funder's form | `requirements.pages[]`, `questions_status`, `requirements_job` | `questions_status`: `found`, `not_found`, `standard` (fallback 6 sections, label "Standard sections: the funder's own questions weren't found") |
| Read again | `POST /v1/applications/{id}/requirements/jobs`, poll `requirements_job` | Busy copy "Reading the funder's pages…" |
| Paste the form | `POST …/requirements/paste` `{ text }` (20–100k chars) | Modal with a `TextArea`; hint "Copy every question from the funder's portal, including limits like '500 words'." |
| Upload the PDF | `POST …/requirements/paste` `{ pdf_base64 }` | PDF under 8 MB; on `422` "We couldn't read this PDF. Paste the questions instead." |
| Words to know | `terms[]` (`TermExplained`) | Sorted by code: at risk, action needed, check, have, info. Collapsed list shows non-`info` items; "Show all" shows the rest |
| Questions | `questions[]`, `answers[]`, checklist items `kind: "question"` | Funder's label and prompt verbatim; limit from `question.limit` |
| Draft all | `POST …/answers/draft-all`, poll `answers_job` | Skips human-edited answers |
| Redraft one | `POST …/answers/{key}/draft` `{ confirm_overwrite }` | `409 human_edit` → confirm dialog "Staff edited this answer. Replace it with a new draft?" |
| Edit | `PATCH …/answers/{key}` `{ text }` | Debounced 1 s; `origin` becomes `human` |
| To do | `checklist.inputs_needed[]` grouped by `owner`; checklist items `kind: "prep"`, `"attachment"` | |
| Answer once | `POST …/facts` `{ need, answer }`; empty answer removes it | After saving, the row shows "Saved. Redraft the answers that need it." with a "Redraft" link per `question_key` |
| Ready | `checklist.complete`, `POST …/stage` `{ to: "ready", override_reason? }` | Not complete → dialog asking for a reason (≥ 10 chars), saved in Activity |
| Export | `GET …/export.md` | |

## 4. A term row (`TermRow`)

Every translated term shows the same 4 parts, in this order:

| Part | Field | Copy / rule |
|---|---|---|
| Term + status | `term`, `status`, `owner` | `Badge` tones: at risk = danger, action needed = warning, check = info, have = success, info = neutral. Owner as text: "Program", "Finance", "Director" |
| What the funder said | `quote`, `url` | In quotes, verbatim, with "View on funder's page ↗" (or "From your pasted form" when `url` is `pasted`) |
| What it means | `plain`, `todo`, `detail` | `plain` first, then `todo` as "What to do: …", then `detail` (e.g. "Usually takes about 10 days; 9 left.") |
| Where this explanation comes from | `explained_by`, `source_url` | `official`: "Source: {host} (official) ↗". `funder`: "The funder's own definition". `hope`: "Hope's grant glossary". `ai`: "Hope's best reading. Check with the funder." and an `info` badge. Never hide this line |

## 5. States and exact copy

- **Locked** (before `drafting`): SC28's "Drafting unlocks after program and director approval."
- **Reading:** "Reading the funder's pages…" with `Loading`.
- **No questions found:** "We couldn't find this funder's questions on its public pages. They're often behind the portal login. Paste them or upload the form PDF." Buttons: Paste, Upload, "Use standard sections".
- **Pages blocked:** under the form panel, "{n} pages couldn't be read (the site blocked us)", listing each URL.
- **No terms:** hide "Words to know".
- **Over limit:** count turns red, "{n} over the {limit} limit". Ready stays blocked.
- **To confirm:** `[TO CONFIRM: …]` markers highlighted in the textarea, listed under the answer and in To do.
- **Errors:** `ErrorNotice` with retry; transient notices wrapped in `AutoDismiss`.

## 6. Accessibility and responsive

- Each answer `TextArea` is labelled with the funder's question label; the limit and count are in `aria-describedby`.
- Term status and owner are text, not only colour. Source links say where they go.
- Questions are a disclosure list (`button[aria-expanded]`), keyboard-operable.
- One column below `lg`; To do comes after the questions.

## 7. UI standards

Use only the existing kit: `Panel`, `StageBar`, `btnPrimary`/`btnSecondary`, `input` (`components/hope/ui.tsx`),
`Badge`, `Button`, `TextArea`, `Modal`, `Loading`, `ErrorNotice`, `EmptyState`, `AutoDismiss`
(`components/ui`), glass tokens in `app/globals.css`. No new colours or fonts. Strings go in
`lib/hope/i18n.ts` (EN and ES).

## 8. Acceptance criteria

1. Given a pasted portal form, every question shows in the funder's words with its limit.
2. Every term with a plain meaning shows the funder's sentence and where the meaning came from; `ai` meanings are labelled.
3. To do groups `inputs_needed` by owner; at-risk items come first.
4. Answering a to-do once and redrafting removes that `[TO CONFIRM]` from the answer.
5. A human edit is never overwritten without the confirm dialog.
6. "Mark ready" is blocked until the checklist is complete, unless a reason is given.
7. Nothing on the screen submits to the funder.

## 9. Open questions for the team

1. Words to know: one list above the questions (as drawn) or inline under each question that uses the term?
2. Should "Answer once" live only in To do, or also under each answer that needs it?
3. Owners are roles today; do we assign named people?
