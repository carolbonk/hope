# SCxx: <Screen name>

| | |
|---|---|
| Route | `/path/[param]` |
| Feature folder | `apps/web/features/<feature>/` |
| Built by | Sxx |
| Primary users | role(s) who come here most, and how often |
| Can act | roles allowed to take each action |
| Status | Draft / Ready / Done |

Write this as a UX lead. A designer and an engineer should be able to build the screen from
this spec alone, without asking a question. Use `screens/SC03-opportunity-matrix.md` as the
reference for the level of detail.

## 1. Purpose and user goals

Who arrives here, from where, and with what job to be done. List the top 3 questions the
screen must answer within 5 seconds, and the one primary action.

## 2. Information hierarchy

What the eye should see first, second and third, and why. What is deliberately hidden
behind a click, and why.

## 3. Wireframe

ASCII wireframe for desktop (>= 1024 px), with every region labelled. Add a second
wireframe for mobile (<= 640 px) whenever the layout changes.

## 4. Content inventory

Every piece of information on the screen:

| Element | Source (endpoint + JSON field) | Format and example | Rules (sorting, truncation, colour/icon, thresholds) |
|---|---|---|---|

## 5. Components

Each region, mapped to the design-system primitive (`Card` `glass-panel`, `Table`, `Input`
`glass-inset`, `Button` with `glass-active` when active, `Badge`, `Modal`, `Drawer`) and its
variants. Name any new shared primitive under "Shared contract additions" instead of
building it inside the feature.

## 6. Interactions

Numbered: the user action, the API call (method + path + body), the pending UI, the
success result, and the result for each error `code`. Include keyboard shortcuts and
deep links (URL query parameters that preserve filters and selection).

## 7. States and exact copy

The exact UI text for each state: loading (skeleton shape), empty (each distinct reason),
filtered-to-empty, error (each `code`), permission denied, stale artifact, offline.

## 8. Data and endpoints

| Trigger | Call | Fields used | Cache / refetch |
|---|---|---|---|

## 9. Responsive behaviour

What collapses, stacks, or moves into a drawer at each breakpoint.

## 10. Accessibility

Tab order, focus on open/close, ARIA roles and labels, live regions, status shown by icon or
text and not colour alone, contrast, `prefers-reduced-motion`.

## 11. Fixture data

What `api/<feature>/fixture.ts` returns so that every state above can be shown without a
backend (list each fixture case).

## 12. Analytics and success measures

Events to log (name and properties) and the metric that says the screen works.

## 13. Acceptance criteria

- [ ] AC1 ... (each maps to a Vitest + Testing Library test, or to a Playwright test for flows)

## 14. Test plan

| AC | Test (file::name) |
|---|---|

## 15. Open questions

With a recommended default for each.
