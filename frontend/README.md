# Dashboard

React dashboard for Ledger Recon. Use Node.js 24 and `npm ci`.

- `npm run dev:demo`: browser-only sample, no API needed.
- `npm run dev`: connected workflow through the Vite proxy to localhost:8000.
- `npm run build`: static production bundle; defaults to demo without an API URL.
- `npm run build:demo`: explicit demo bundle.
- `npm test`: demo adapter (filters, search, bulk review, exact sorting and statistics) and formatting.
- `npm run test:browser`: Chromium workflow checks against the built demo (triage, keyboard review, bulk resolve, themes, mobile). Run `npx playwright install chromium` once.
- `npm run lint` / `npm run format:check`: code checks.

For Vercel, use this directory as the project root. See the [project README](../README.md) and [deployment guide](../docs/deployment.md) for run modes and environment variables.
