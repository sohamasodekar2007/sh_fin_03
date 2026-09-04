# Frontend snippets

Three drop-in components matching `sh_fin_03/apps/web`'s existing Tailwind
tokens (`bg-surface`, `border-line`, `text-ink`, `text-inkFaint`,
`font-display`) and using dependencies already in that project's
`package.json` (`recharts`, `lucide-react`) — no new npm installs needed
on merge.

They are **not wired into the Next.js build here** (this addon folder has
no `node_modules`/`next` project of its own on purpose — see
`../MERGE_GUIDE.md`). Treat them as ready-to-copy source files.

## Wiring them up on merge

1. Copy the three `.tsx` files into `sh_fin_03/apps/web/components/dashboard/`.
2. Add `NEXT_PUBLIC_ADDON_API_URL=http://localhost:8100` to
   `apps/web/.env.local` (or point it at wherever you deploy the addon
   API / the merged routes, once folded into the real backend).
3. Drop each component into `apps/web/app/dashboard/page.tsx` next to its
   sibling:
   - `<SpendVelocityCard />` next to `KpiCards`
   - `<CostBreakdownPanel />` next to `ResourceTable`
   - `<UnitEconomicsCard />` next to `HealthDonut`
4. Each component calls its own demo endpoint
   (`/spend-velocity/demo-alert`, `/cost-attribution/demo-breakdown`,
   `/unit-economics/demo-summary`) by default. Once the backend exposes
   real routes (see MERGE_GUIDE.md), change the fetch URL to the real
   endpoint and pass real request bodies instead of relying on the
   `-demo-*` GET routes.

## Why no chart library dependency was added

`CostBreakdownPanel`'s bars are plain styled `<div>`s, not a `recharts`
`<BarChart>`, even though `recharts` is already a dependency. A cost
*attribution ranking* (a handful of labeled bars with a delta and a
percentage) doesn't need a charting library's axes/tooltip machinery —
plain divs render identically, stay themeable with the existing Tailwind
tokens, and avoid coupling this snippet to a specific recharts version.
Swap in `recharts` later if you want animated transitions between
refreshes; the data shape (`Contributor[]`) works either way.
