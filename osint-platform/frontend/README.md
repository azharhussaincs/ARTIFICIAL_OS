# OSINT Platform — Frontend (Next.js 14)

Premium cyber-intelligence dashboard for the OSINT Platform backend.
Built with Next.js 14 (App Router) + Tailwind + Framer Motion +
Cytoscape + Lucide. The backend FastAPI service is required.

## Stack

| Layer | Library | Why |
|---|---|---|
| Framework  | **Next.js 14** App Router (TypeScript) | RSC + edge-friendly, native `EventSource` proxy via `rewrites()` |
| Styling    | **Tailwind CSS 3** + custom palette + glassmorphism utilities | dark cyber theme |
| Motion     | **Framer Motion 11** | page transitions, stagger, hover glow, expand/collapse |
| Graph      | **Cytoscape 3** + cose-bilkent layout | neon nodes, verified-pulse, force-directed layout |
| Icons      | **Lucide React** | crisp line icons for the intelligence look |
| Fonts      | Inter, Space Grotesk, JetBrains Mono (via Google Fonts) | technical, premium |
| Type       | **TypeScript strict** | matches backend contracts in `app/lib/types.ts` |

## Quick start

You need the FastAPI backend running first (default at
`http://localhost:8000`). See `../backend/README.md`.

```bash
cd osint-platform/frontend
cp .env.local.example .env.local              # optional: change NEXT_PUBLIC_API_BASE
npm install                                   # ~ 90 s first time
npm run dev                                   # http://localhost:3000
```

`npm run dev` starts Next on `:3000`. The `/api/*` paths are proxied to
the backend via `next.config.mjs:rewrites()`, so the SSE stream and all
fetches just work.

### Production build

```bash
npm run build
npm start                      # serves on :3000
```

In production behind a reverse proxy you'd typically:
- terminate TLS at the proxy (Caddy / Nginx / Traefik)
- route `/api/*` to the FastAPI container
- route everything else to the Next container

## Where things live

```
frontend/
├── app/
│   ├── page.tsx                       # one-page assembly
│   ├── layout.tsx + globals.css       # fonts, dark theme, glassmorphism utilities
│   ├── lib/                           # api client, types (mirrors backend), formatters
│   ├── hooks/                         # useSearchStream (SSE), useCounter, useKeyboard
│   ├── store/uiStore.ts               # tiny global UI state (no Redux/Zustand)
│   └── components/
│       ├── shell/      # Sidebar, TopBar, CommandPalette (⌘K)
│       ├── hero/       # SearchHero with animated grid + particles + scanner
│       ├── ui/         # GlassCard, NeonButton, Badge, Skeleton, ScannerOverlay
│       └── dashboard/  # MetricCard (animated counters), ConfidenceRing,
│                       # FindingsList + FindingCard + SignalTrail,
│                       # IdentityGraph (Cytoscape), LiveTerminal (SSE),
│                       # Timeline, DorksPanel, WhoisPanel, SnapshotsPanel, HistoryPanel
└── tailwind.config.ts                 # cyber palette, scan/blink/shimmer/drift keyframes
```

## UX features

- **Animated headline** with rotating typed words ("a name." → "an email." …)
- **Scanner sweep** overlay across the search panel while a search runs
- **Live terminal** (SSE-driven) showing each engine pass with stage colors
- **Cytoscape identity graph** — neon nodes color-coded by type, **verified
  nodes pulse**, seed node is a diamond
- **Findings cards** with expandable signal trail (`+25 cross_platform_handle`,
  `−40 unrelated_domain`, `Σ = 75 → clamp(0,100)`)
- **Confidence ring** — animated SVG, colored by tier
- **⌘K command palette** with type-to-filter (also ESC to close, `/` to focus search)
- **Glassmorphism** + neon-border treatment on every card
- **Mobile responsive** — sidebar collapses into a slide-in drawer
- **CSV / PDF export** buttons in the Findings card header (uses backend export endpoints)

## Keyboard shortcuts

| Key | Action |
|---|---|
| `⌘ K` (or `Ctrl K`) | Open the command palette |
| `/`  | Focus the search input |
| `Esc` | Close the command palette |
| `Enter` | Submit search (in input) |

## Pointing at a different backend

```bash
echo "NEXT_PUBLIC_API_BASE=https://api.your-domain.com" > .env.local
npm run dev
```

Both the proxied `/api/*` rewrites and the SSE `EventSource` use this base.

## Notes

- The frontend is **stateless** — every render derives from the backend
  response. There is no client-side persistence beyond browser session.
- The backend's static-served fallback dashboard at `/` (in
  `backend/app/static/index.html`) still works if you don't want to run
  the Node app. This Next frontend is the premium UI; the static one is
  the no-build, single-file alternative.
