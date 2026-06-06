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
