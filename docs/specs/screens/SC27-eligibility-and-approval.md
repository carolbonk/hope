# SC27: Application workspace: eligibility and internal approval

| | |
|---|---|
| Route | `/hope/applications/[oppId]` (stages `saved`, `eligibility`, `approval`) |
| Files | `apps/web/app/hope/applications/[oppId]/page.tsx` (`Workspace`, `EligibilityPanel`, `ApprovalPanel`, `CommentsPanel`) |
| Built by | H4 (ported in PR #34) |
| Primary users | Grants lead of a small nonprofit, plus whoever plays "Program" and "Director" in the demo |
| Can act | Online: any signed-in member (roles not assigned yet; the server records who and when). Demo mode: anyone in this browser |
| Status | Built: server-backed online (`/v1/applications/{id}/*`), browser-only in demo mode |

## 1. Purpose and user goals

The user arrives from Saved (`/hope/saved`), Deadlines or a saved card in Discover. Within 5 seconds the
screen answers:
1. **Where are we?** The stage bar (`saved → eligibility → approval → drafting → ready`) and "Next action".
2. **Can we apply?** The eligibility checklist and its result: Meets / Not qualified / Needs review.
3. **What do we still need?** The required documents, with their status from the dossier.

**Primary action:** the stage button ("Start eligibility review" → "Send to internal approval").
**Secondary actions:** set Yes/No/Unknown with evidence, approve or send back, add a comment, open the dossier.

## 2. Layout (desktop; mobile stacks the columns)

```text
[hope✳ nav: Discover · Saved · Deadlines        EN|ES · Account ▾]
Funder (demo) · Opportunity name              $25,000–$50,000 · Due in 21 days
[ StageBar: saved ▸ eligibility ▸ approval ▸ drafting ▸ ready ]
Next action: Confirm every requirement with evidence, then send to internal approval.   [Send to internal approval]
┌ Eligibility checklist ───────────────┐ ┌ Required documents ────────────┐
│ 501(c)(3)   (Yes)(No)(Unknown)       │ │ Board list · Declared          │
│ From your profile · Declared         │ │ Child protection · Pending     │
│ Evidence / note [...............]    │ │ Update in your dossier →       │
└──────────────────────────────────────┘ └────────────────────────────────┘
┌ Internal approval ───────────────────────────────────────────────────────┐
│ Program review: Pending  [Approve] [Send back]   comment [.........]     │
│ Director review: Waits for program review                                 │
└───────────────────────────────────────────────────────────────────────────┘
[ Application draft (SC28, locked until both approvals) ]
[ Internal review comments ]   [ Activity ▸ ]
```

## 3. Content and rules

| Element | Source | Rule |
|---|---|---|
| Header | `Opportunity` (`funder`, `name`, `amountMin/Max`, `currency`, `deadline`) | "(demo)" funders are fictional; `DemoTag` always shown |
| Stage bar | `app.stage` | Current stage highlighted; past stages ticked |
| Requirement row | `opp.requirements[]`, `requirementStatus` | Evidence > profile fact > Unknown. Unknown is never shown as No |
| Result | `eligibility(opp, profile, app)` | `meets` (all Yes), `not_qualified` (any No), `needs_review` (any Unknown) |
| Documents | `oppDocs(opp, profile)` | Status from the dossier; expired → pending; empty → "This call lists no specific documents (demo)…" |
| Approvals | online `view.approvals[step]` (`by`, `at`); demo `app.approvals.program/director` | Online "Approved by {name} · {time}"; demo "Approved (simulated)"; plus "Pending", "Sent back" |

## 4. Interactions

1. **Start eligibility review** (`saved` → `eligibility`).
2. **Yes / No / Unknown + note:** writes `app.evidence[reqId]`. The result updates immediately.
3. **Send to internal approval:** disabled while any requirement is No or Unknown. The hint reads "Resolve unknown or failed requirements first."
4. **Program review: Approve.** This enables Director review.
5. **Send back:** needs a comment ("Add a comment explaining what to change."). The stage returns to `eligibility`.
6. **Director review: Approve:** the stage becomes `drafting`, and SC28 unlocks.
7. **Add comment:** appends to `app.comments` (author "You (local)").

Online, steps 1-7 are the H4 server calls (`…/stage`, `…/evidence`, `…/approvals`, `…/comments`) with `If-Match`;
the page shows the returned application. The note is sent when the field loses focus. A version conflict (412)
reloads with "Someone else changed this application. We loaded the latest version."; a 409/422 shows the server's
message, both in a 5-second notice under the header.

## 5. States and exact copy

- **Not in this browser:** "This application isn't in this browser. It may have been saved in another browser or cleared."
- **Approval note:** online "Any signed-in teammate can approve for now. Hope records who approved and when."; demo
  mode keeps the "Simulated roles" note.
- **Eligibility locked (online, after eligibility):** "Eligibility is locked while the application is in review."
- **Loading (online):** "Loading this application…"
- **Eligibility note:** "Eligibility here is specific to this call. It is separate from “profile complete” and “documentation reviewed”."
- **Storage:** "Saved in this browser only — not shared, not production storage, no real sign-in."

## 6. Accessibility and responsive

- Every control has a visible label, a focus ring and a minimum 44 px height.
- Status is never shown by colour alone.
- The language toggle sets `<html lang>`.
- Below `md`, the panels stack in reading order.

## 7. Acceptance criteria

The same as H4 AC1-AC7.
