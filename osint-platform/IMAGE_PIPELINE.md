# Image Intelligence Module

End-to-end design + diagnostic guide for avatar discovery, cross-platform
matching, and verification.

---

## TL;DR

```
seed (name/email/phone/username)
     │
     ▼
 username probe ────► confirmed profile URLs
     │
     ▼
 [for each profile]
   ┌─────────────────────────────────────────────────────────┐
   │  ProfileFetcher.fetch()                                 │
   │  ├ HTML 200      → fingerprint parser → og:image / etc. │
   │  ├ HTML 4xx/5xx  → salvage og:image from error body     │
   │  └ no avatar yet → direct_avatar_url(platform,handle)   │
   │                    (GitHub /USER.png, GitLab, …)        │
   └─────────────────────────────────────────────────────────┘
     │
     ▼
 [filter] _is_platform_default_image()  drops site-default share images
     │
     ▼
 AvatarFingerprinter.hash_many()  ─► dHash 64-bit per avatar
     │
     ▼
 cluster_by_hash(threshold=12)    ─► groups across platforms
     │
     ▼
 emit `image::sha:<hash>` Finding + IMAGE_MATCH(+20) on profiles
     │
     ▼
 frontend  ─►  GET /api/image?url=…  ─► server-side proxy + LRU
              <ImageThumb> with hover-zoom + verified badge
```

---

## Why images go missing — and what we now do about it

| Failure mode | Root cause | Fix |
|---|---|---|
| Profile fetch returns 403/429 | Platform's bot-detection serves a non-200 with full HTML body | `profile_match.fetch()` parses the body anyway and salvages `og:image` |
| Profile fetch returns generic page (login wall, Cloudflare) | `_looks_blocked` catches it; `og:image` is the **site's marketing share-image**, not the user's | `_is_platform_default_image()` filters known logo paths (GitHub social.png, Twitter sticky, Instagram static, etc.) |
| Site uses JS-rendered avatars not in SSR HTML | Some sites only ship the avatar via client-side fetch | `direct_avatar_url(platform, handle)` returns a deterministic CDN URL for GitHub & GitLab — works for every confirmed profile, no scraping needed |
| Email seed has no avatar | We never fed Gravatar into the image pipeline | Email seeds now synthesize a `gravatar` snapshot up-front; it joins the cluster pipeline naturally |
| `<img src=…>` blocked by CDN hot-link / Referer / COEP | The browser silently fails | All avatars go through `GET /api/image?url=…` (server-side fetch, in-memory LRU cache, SSRF guard) |
| Snapshot dropped because `is_blocked=true` | Defensive code excluded blocked profiles from the legacy result views | Now always emitted; `is_blocked` is just a UI flag |

---

## Avatar source priority (tried in order)

Defined in `backend/app/osint/fingerprints.py:_meta_image()`:

1. Per-platform CSS selector (e.g. `img.avatar-user` on GitHub) — most specific
2. `og:image:secure_url`
3. `og:image`
4. `twitter:image`, `twitter:image:src`
5. JSON-LD `image` (string / `{url:...}` / array)
6. JSON-LD `thumbnailUrl`, `logo`
7. `<link rel="image_src">`
8. `<link rel="apple-touch-icon">` (favicons explicitly skipped)
9. **Fallback:** `direct_avatar_url(platform, handle)` — currently GitHub & GitLab

After every step we run `_is_platform_default_image()`. Any URL containing
fragments like `githubassets.com/images/modules`, `abs.twimg.com/sticky/default_profile_images`,
`instagram.com/static/images/`, `default_avatar`, `favicon`, etc. is rejected.

---

## Verification rules

A `social_profile` Finding is "verified" (`verified=true`, label ≥ `high`) when
its `confidence` reaches **≥ 70**. The relevant signals:

- `+30` profile_hit (200 OK on the platform)
- `+30` cross_platform_handle (same handle on ≥ 2 platforms)
- `+20` image_match (avatar in a multi-platform cluster — see below)
- `+25` name_match (display name matches another profile's)

An `image` Finding (the cluster) is its own first-class entity:

- Keyed by `image::sha:<hash-hex>` — stable across searches
- Created only when the cluster spans ≥ 2 distinct platforms
- Base `+30 profile_hit` + per-cluster `+20 image_match` bonus
- Linked to every social_profile and username it ties together

So for a 3-platform avatar cluster, the linked username gets:
`+15 (probe) +30 (cross_platform) +25 (name_match) +20 (image_match) = 90 ⇒ "verified"`.

---

## Diagnostics — how to tell what's actually happening

The dashboard now shows a 3-up status strip below the main metrics:

```
[ Avatars extracted ]   [ Image clusters ]   [ Image findings ]
        7                       2                    2
```

Plus the engine timeline emits a `[image]` stage line:

```
[image]  hashing 7 avatar(s) for cross-platform match
```

If you see `Avatars extracted: 0` despite confirmed profiles, the most
likely causes (in order):

1. The profiles are on platforms with no per-platform fingerprint AND no
   `og:image` AND no direct-avatar pattern — open `app/osint/fingerprints.py`
   and check that platform's parser is registered in `PARSERS`.
2. All fetches returned non-200 AND the platform isn't in
   `DIRECT_AVATAR_BUILDERS` — add a builder if a public pattern exists.
3. The avatars all matched `_is_platform_default_image()` — your test
   targets are probably login-walled accounts; try GitHub or Dev.to
   (which don't gate anonymous viewers).

If `Avatars extracted` is nonzero but the UI still shows broken images:
the proxy is the culprit. Check the browser Network tab for failing
`/api/image?url=…` requests and the FastAPI log for the upstream error.

---

## Where each fix lives in the codebase

| Capability | File |
|---|---|
| Image proxy + LRU + SSRF guard | `backend/app/api/image_proxy.py` |
| Direct-avatar URL builders + Gravatar | `backend/app/osint/image_match.py` |
| Platform-default image filter | `backend/app/osint/fingerprints.py` (`_is_platform_default_image`) |
| Multi-source `og:image` extractor | `backend/app/osint/fingerprints.py` (`_meta_image`) |
| HTTP-error avatar salvage | `backend/app/osint/profile_match.py` |
| Always-emit-snapshot policy | `backend/app/osint/correlation.py` (`_fetch_profile_snapshots`) |
| Email-seed Gravatar synth | `backend/app/osint/correlation.py` (`run_bundle`) |
| dHash + clustering + IMAGE_MATCH signal | `backend/app/osint/image_match.py` + `correlation.py:_image_correlate_pass` |
| `image` Finding type | `backend/app/osint/verification.py` |
| `<ImageThumb>` proxy-routed component | `frontend/app/components/ui/ImageThumb.tsx` |
| FindingCard avatar resolution | `frontend/app/components/dashboard/FindingCard.tsx` |
| Image cluster panel | `frontend/app/components/dashboard/ImageClustersPanel.tsx` |
| Diagnostics strip | `frontend/app/page.tsx` |
| Static fallback proxy routing | `backend/app/static/app.js` |

---

## Quick smoke test

```bash
source onve/bin/activate
cd osint-platform/backend
python3 -c "
import sys; sys.path.insert(0, '.')
from app.osint.image_match import direct_avatar_url, gravatar_url
from app.osint.fingerprints import _is_platform_default_image
print(direct_avatar_url('github', 'octocat'))
print(gravatar_url('jane@example.com'))
print(_is_platform_default_image('https://github.githubassets.com/images/modules/x.png'))
"
```

Expected:
```
https://github.com/octocat.png?size=256
https://www.gravatar.com/avatar/9e26471d35a78862c17e467d87cddedf?s=256&d=404
True
```

And the live proxy (with backend running):
```bash
curl -i 'http://localhost:8000/api/image?url=https://github.com/octocat.png'
```

Should return `200 image/png` with `X-Proxy-Cache: MISS` (then `HIT`
on the second call).
