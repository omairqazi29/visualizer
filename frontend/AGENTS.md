<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

# Frontend-Specific Policy & Data Notes

## Methodology Page (`/methodology`)
- Renders live model parameters from the `/api/methodology` backend endpoint.
- Shows: data sources (with links), legal/policy status, restricted country list, model constants.
- **When updating backend constants** (`src/constants.py`) or the methodology endpoint (`api/main.py`), verify the frontend page still renders correctly.
- The page auto-reflects backend changes — no frontend edits needed for data/policy updates unless adding new sections.

## Data Source References
- The Overview page (`page.tsx`) has a static "Data Sources" card. If coverage dates change significantly, update the labels there too.
- All API calls go through `src/lib/api.ts`. The `getMethodology()` call and `MethodologyData` interface must stay in sync with the backend `MethodologyResponse` Pydantic model.

## Supply Model Sync (CRITICAL)
All supply numbers come from the centralized model in `src/engine/supply.py`. **No page may hardcode supply results.**

Data flow: `supply.py` → `api/main.py` (Pydantic) → `src/lib/api.ts` (TypeScript types) → page components.

When the backend supply model changes:
1. **API types** (`src/lib/api.ts`): Add/update fields to match the `SupplyBreakdownResponse` Pydantic model in `api/main.py`.
2. **Waterfall page** (`app/waterfall/page.tsx`): Update methodology text to match actual calculation logic (e.g., EB-4/5 source, India share method). This page has descriptive text explaining each waterfall step — it must match `supply.py`.
3. **Supply-demand page** (`app/supply-demand/page.tsx`): Uses API data directly — no text to update, but verify new fields render if applicable.
4. **Overview page** (`app/page.tsx`): Fetches from API — verify summary cards still make sense.
5. **Never** compute supply locally in a page component. Always fetch from the API.
