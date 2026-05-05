# Noise Model

This document describes **what the platform refuses to treat as identity
evidence**, and why. The previous version produced too many findings
because every outbound link from a profile page became a "related
website" — including GitHub footer links, CDN URLs, help pages, and
platform marketing text. This file captures the rules we now apply at
the source.

## 1. Where filtering happens

Every candidate identifier passes through `app/osint/relevance.py`
*before* reaching `FindingStore.upsert()`. There is exactly one chokepoint;
no other module gets to bypass it.

```
candidate value (URL / handle / email / bio / display_name)
        │
        ▼
 ┌──────────────────────────────────────────┐
 │ relevance.py                             │
 │   • is_noise_url(url)                    │  → drop
 │   • is_generic_platform_text(text)       │  → drop
 │   • relevance_to_seed(value, …)          │  → keep, with delta
 └──────────────────────────────────────────┘
        │
        ▼
 FindingStore.upsert(...)  ← only "clean" candidates reach here
```

## 2. Domain denylist (`PLATFORM_OWNED_DOMAINS`)

Hosts that are **platform infrastructure**, not personal identity. A
match (or any subdomain match) drops the URL silently. Categories:

| Category | Examples |
|---|---|
| GitHub | `github.com`, `*.github.io`, `githubusercontent.com`, `githubassets.com`, `docs.github.com`, `support.github.com` |
| GitLab | `gitlab.com`, `gitlab-static.net`, `about.gitlab.com` |
| Twitter/X | `twitter.com`, `x.com`, `t.co`, `twimg.com`, `help.twitter.com` |
| Meta | `facebook.com`, `instagram.com`, `cdninstagram.com`, `threads.net`, `whatsapp.com` |
| LinkedIn | `linkedin.com`, `licdn.com`, `lnkd.in` |
| Google / YouTube | `youtube.com`, `youtu.be`, `googleusercontent.com`, `gstatic.com`, `policies.google.com` |
| TikTok | `tiktok.com`, `tiktokcdn.com`, `bytedance.com` |
| Reddit | `reddit.com`, `redd.it`, `redditstatic.com` |
| Medium / Substack | `medium.com`, `substack.com`, `policy.medium.com` |
| Dev.to | `dev.to`, `forem.com` |
| Stack Exchange | `stackoverflow.com`, `stackexchange.com`, `imgur.com` |
| Dev ecosystem | `npmjs.com`, `hub.docker.com`, `keybase.io`, `hackerone.com` |
| Generic CDN / consent | `cookielaw.org`, `onetrust.com`, `cloudflare.com`, `cloudfront.net`, `jsdelivr.net`, `unpkg.com` |
| Public mailbox | `gmail.com`, `outlook.com`, `icloud.com`, `proton.me`, etc. |

Why public mailboxes are denylisted as **domains**: an email like
`jane@gmail.com` is correctly treated as a personal email, but
`gmail.com` itself is not Jane's domain. We never RDAP-look up these.

## 3. Path patterns (`IGNORE_PATH_PATTERNS`)

Even on permitted hosts, paths matching this regex are dropped:

```
about | terms | privacy | legal | cookies | gdpr | dmca | copyright
help | support | docs | api | developers | status | security | sitemap
login | signin | signup | register | join | password | reset
pricing | enterprise | business | advertis | press | jobs | careers
blog | newsroom | news | community | events | conferences
explore | trending | discover | search | browse | categor* | tags
download | apps | mobile | extension | widget | embed | share
partners | affiliates | sponsors | brand | guidelines
feed | rss | atom | opml | sitemap.xml | robots.txt | favicon.ico
opensearch | manifest.json | service-worker
```

## 4. Static-asset extensions

Files with these extensions are dropped — they're not identities:

```
.png .jpg .jpeg .gif .svg .webp .ico .bmp .tiff .heic
.css .js .mjs .map .woff .woff2 .ttf .otf .eot
.mp4 .webm .mov .m4a .mp3 .wav .ogg .flac
.pdf .zip .tar .gz .bz2 .xz .7z .rar
```

## 5. Generic platform text (`GENERIC_PLATFORM_TEXT`)

Bios and display names matching any of these patterns are dropped:

| Pattern | Matches |
|---|---|
| `^tiktok.*make your day` | "TikTok - Make Your Day" |
| `^github.*where the world builds software` | GitHub generic OG title |
| `^linkedin.*log in` / `^join linkedin` | LinkedIn login walls |
| `^sign in` / `^log in` | Generic auth-wall titles |
| `^reddit.*front page of the internet` | Reddit homepage OG |
| `^medium.*where good ideas find you` | Medium homepage OG |
| `^enjoy the videos and music you love` | YouTube homepage OG |
| `^just a moment` / `^attention required` | Cloudflare challenge |
| `^are you a robot` / `^access denied` | Generic block pages |
| `^profile` / `^home` / `^community` | Bare nav titles |

A bio is also dropped if it is **>600 characters** (almost always page
text, not a personal bio) or **<2 characters**.

## 6. Per-platform fingerprints

`app/osint/fingerprints.py` extracts only the user's own content:

| Platform | Display name | Bio | Personal links |
|---|---|---|---|
| GitHub | `span.p-name.vcard-fullname` | `div.p-note.user-profile-bio` | `.vcard-details a[rel~="me"]` + `[data-test-selector="profile-social-link"]` |
| GitLab | `.user-info .name` | `.user-info .user-bio` | `.user-info a[itemprop="url"]` |
| Dev.to | `h1.crayons-title` | `.profile-header__summary` | `.profile-header__meta a` |
| Medium | OG title (strip ` – Medium`) | OG description | — |
| Reddit | OG title (strip `u/`) | OG description | — |
| YouTube | OG title | OG description | — |
| About.me | `h1` | OG description | `a[rel="me"]`, `.links a` |
| Keybase | `.display_name` | `.bio` | `.proofs a` |
| anything else | OG title (with generic-text gate) | OG description (gated) | — |

Pages flagged as blocked (login wall / Cloudflare) emit a snapshot with
`is_blocked=true` and `parser_confidence=0.2`; the correlation engine
ignores their text content but keeps the avatar and the fact that the
profile exists.

## 7. Email role-mailbox filter

Emails whose local-part is in this set are dropped (they're org
shared inboxes, not personal identities):

```
noreply, no-reply, donotreply, support, help, info, contact, hello, hi
admin, administrator, postmaster, webmaster, abuse, security, privacy
press, media, sales, billing, accounts, marketing, team, office
feedback, subscriptions, newsletter
```

## 8. RDAP gating

Domain-RDAP lookups are skipped for:
- public mailbox providers (`gmail.com`, etc.)
- platform-owned domains (`github.com`, `instagram.com`, etc.)

so we don't burn lookups on the registry's own contact data.

## 9. Recursion gate

Recursive handle re-probing in the engine is capped at
`MAX_RECURSIVE_HANDLES = 4` and only consumes handles that came out of a
**verified profile's bio** — never from page chrome or footer text.

## 10. Diagnostic output

The engine returns a `suppressed_count` in every search response — the
number of candidate identifiers we threw away. The dashboard surfaces
this so analysts can sanity-check that the gate isn't *too* aggressive.

If you find a real identifier being suppressed, add a regression test
against `app/osint/relevance.py` and tune the rule.
