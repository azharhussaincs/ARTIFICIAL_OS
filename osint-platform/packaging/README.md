# OSINT Platform — Windows packaging

Everything in this folder is **build-time only**. None of it is imported by
the running FastAPI backend or the Next.js frontend. Its sole job is to
turn the existing dev project into a single Windows desktop application
where the end user installs nothing.

The end-user experience is:

1. Download `OSINT-Setup-1.0.0.exe` (or extract `OSINT-Portable.7z`).
2. Run it.
3. The app opens in their default browser at `http://127.0.0.1:<auto>/`.

No Python, Node.js, Java, Elasticsearch, Docker, or environment variables
are required on the target machine.

---

## What gets bundled

- Python 3.11 runtime + every package from `backend/requirements.txt`
- The full FastAPI app (`backend/app/`) — unchanged source
- The Next.js static export (`frontend/out/`) copied into `backend/app/static`
- Elasticsearch 8.15.x **with bundled OpenJDK** (~600 MB)
- A zstd-compressed Elasticsearch snapshot of your dev index (~3–6 GB
  for an 18 GB index, depending on data shape)
- Launcher (`OSINT.exe`) that supervises everything

---

## Folder layout

```
packaging/
├── launcher.py                # OSINT.exe entry point (PyInstaller --windowed)
├── osint.spec                 # PyInstaller build spec
├── es-config/
│   ├── elasticsearch.yml      # locked-down single-node config
│   └── jvm.options            # JVM tuning (heap injected at runtime)
├── hooks/
│   └── hook-elasticsearch.py  # PyInstaller hook for elasticsearch[async]
├── installer/
│   └── osint.iss              # Inno Setup script
├── scripts/
│   ├── build.bat              # full Windows build orchestrator
│   ├── make_snapshot.sh       # take ES snapshot on Linux dev box
│   ├── make_snapshot.bat      # same on Windows
│   └── prepare_frontend.sh    # Next.js export from Linux
├── assets/
│   └── osint.ico              # OPTIONAL — drop your icon here
└── vendor/                    # gitignored, populated at build time:
    ├── elasticsearch/         # extracted ES with-JDK ZIP
    └── snap_v1.tar.zst        # ES snapshot tarball
```

End-user install layout (created by Inno Setup or by extracting the
portable archive):

```
%ProgramFiles%\OSINT\           (or any folder, for portable mode)
├── OSINT.exe
├── _internal\                  PyInstaller bundle (Python + deps)
├── elasticsearch\              ES + bundled JDK
├── es-snapshot\snap_v1.tar.zst
├── portable.flag.template      rename to portable.flag for portable mode
└── unins000.exe                (installer mode only)

%LOCALAPPDATA%\OSINT\           per-user, writable, survives uninstall
├── es-data\                    where the 18 GB index lives after restore
├── es-logs\
├── es-tmp\
├── es-repo\                    extracted snapshot dir
├── sqlite\osint.db
├── logs\launcher.log
├── exports\
└── .firstrun_done
```

---

## Prerequisites

### On the Linux dev machine (one-time prep)

- The dev FastAPI + Elasticsearch already running (so we can snapshot it)
- `zstd` and `tar` (`apt install zstd tar`)
- Node.js 20 LTS + npm (only if you want to pre-build the frontend on
  Linux — `build.bat` will also do it on Windows)

### On the Windows build machine

- Python **3.11.x** in `PATH`
- Node.js **20 LTS** in `PATH`
- (Optional) [Inno Setup 6](https://jrsoftware.org/isinfo.php) — the
  build script auto-runs `iscc` if it finds it
- (Optional) [7-Zip](https://www.7-zip.org/) — for the portable archive

End-user machines need **none** of the above.

---

## Build pipeline

### Step 1 — take the Elasticsearch snapshot (Linux dev box)

The 18 GB index is shipped as a zstd-compressed snapshot, not as raw
`path.data`. Snapshots are deduplicated and compress dramatically better.

```bash
# Default: ES at http://localhost:9200, index "tc_index"
packaging/scripts/make_snapshot.sh
# -> packaging/vendor/snap_v1.tar.zst
```

Override via env vars if needed:

```bash
ES_URL=http://localhost:9200 \
ES_INDEX=tc_index \
SNAPSHOT_REPO_DIR=/srv/es_snap \
packaging/scripts/make_snapshot.sh
```

> **path.repo gotcha:** the source ES must have `path.repo` configured
> (in its `elasticsearch.yml`) to include `SNAPSHOT_REPO_DIR`. ES refuses
> to register a snapshot repo at any directory not in that allow-list.
> If your dev ES doesn't have it set, add it and restart ES once.

### Step 2 — stage Elasticsearch (Windows build box)

Download the **with-JDK** Windows ZIP:
`elasticsearch-8.15.x-windows-x86_64.zip`

Extract to `packaging\vendor\elasticsearch\` so that
`packaging\vendor\elasticsearch\bin\elasticsearch.bat` and
`packaging\vendor\elasticsearch\jdk\bin\java.exe` both exist.

(The `-no-jdk` variant won't work — there is no Java on the end-user
machine.)

Copy `snap_v1.tar.zst` from step 1 into `packaging\vendor\`.

### Step 3 — run the build (Windows build box)

```cmd
cd packaging\scripts
build.bat
```

`build.bat` does, in order:

1. Pre-flight checks (Python, npm, vendored ES, optional snapshot)
2. `npm ci` + `npm run build` with `NEXT_OUTPUT_EXPORT=1`, copies
   `frontend\out\` into `backend\app\static`. The original `static/` is
   backed up once to `backend\app\.static.backup` so you can restore
   the dev fixture if you want.
3. Creates `.buildvenv\`, installs `backend\requirements.txt`,
   `pyinstaller==6.10.0`, `zstandard==0.22.0`
4. `pyinstaller --noconfirm --clean osint.spec` → `dist\OSINT\OSINT.exe`
5. Copies `vendor\elasticsearch\` into `dist\OSINT\elasticsearch\` and
   overlays our `elasticsearch.yml` + `jvm.options`
6. Copies the snapshot into `dist\OSINT\es-snapshot\`
7. Runs `iscc` (if installed) → `installer\Output\OSINT-Setup-*.exe`
8. Runs `7z` (if installed) → `dist\OSINT-Portable.7z`

Outputs:

| Artifact | Purpose |
|---|---|
| `dist\OSINT\OSINT.exe` | Double-click smoke test |
| `installer\Output\OSINT-Setup-1.0.0.exe` | The installer to ship |
| `dist\OSINT-Portable.7z` | Portable distribution |

---

## Runtime behaviour

When the user double-clicks `OSINT.exe`:

1. `launcher.py` acquires the Windows named mutex
   `Global\OSINT_PLATFORM_SINGLETON`. If a second instance launches, it
   shows a "already running" dialog and exits.
2. Free ports are picked: defaults `9200` (ES) and `8000` (FastAPI),
   falling back to OS-assigned ephemeral ports if they're occupied.
3. Elasticsearch starts as a hidden child process
   (`CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP`). Heap is sized to
   25 % of physical RAM, clamped to `[1024 MB, 4096 MB]`.
4. Launcher polls `_cluster/health?wait_for_status=yellow` for up to
   240 s.
5. On first run only: launcher streams `snap_v1.tar.zst` into
   `%LOCALAPPDATA%\OSINT\es-repo\`, registers it as a fs repo, and
   restores `snap_v1`. A `.firstrun_done` marker prevents re-extraction
   on subsequent launches.
6. Runtime config is injected into `os.environ` (database URL, ES URL,
   ports, CORS origins) **before** `app.main` is imported, so the
   existing pydantic-settings loader picks up the values with no
   backend code change.
7. The FastAPI app instance is augmented in-process with a `/_next`
   StaticFiles mount and a SPA catch-all route, so the Next.js export
   is served correctly without modifying `backend/app/main.py`.
8. The user's default browser opens to `http://127.0.0.1:<api_port>/`.
9. On exit (window closed, signal received, or uvicorn crash), the
   launcher sends `CTRL_BREAK_EVENT` to ES, then `terminate()`, then
   `kill()` if it doesn't shut down within 30 s. Both `atexit` and a
   `try/finally` cover the path.

All logs land in `%LOCALAPPDATA%\OSINT\logs\`:

- `launcher.log` — supervisor decisions (rotated, 5 × 2 MB)
- `es.out.log` / `es.err.log` — Elasticsearch stdio
- `crash.log` — Python tracebacks from the crash handler

---

## Portable mode

If the file `portable.flag` exists next to `OSINT.exe`, the launcher
puts user data in `<install_dir>\userdata\` instead of
`%LOCALAPPDATA%\OSINT\`. The portable distribution ships
`portable.flag.template`; the user just renames it.

Use this for USB-stick deployments or kiosk machines where you want
the entire 18 GB to live in one relocatable folder.

---

## Updates

The Inno Setup script uses a **stable** `AppId` GUID. Future versions
keep the same `AppId` (with a higher `AppVersion`) and Inno treats them
as upgrades:

- `InitializeSetup()` silently runs the previous uninstaller first
- `[UninstallDelete]` only removes state inside `{app}\`; user data in
  `%LOCALAPPDATA%\OSINT\` is preserved across upgrades **and** across
  uninstall — so the 18 GB is downloaded once.

To ship a new version:

1. Bump `AppVersion` in `osint.iss`.
2. If the snapshot changed, regenerate `vendor\snap_v1.tar.zst` and
   delete `%LOCALAPPDATA%\OSINT\.firstrun_done` on test machines so the
   restore re-runs. (For end users, change the snapshot filename to
   e.g. `snap_v2.tar.zst` and update `SNAPSHOT_ARCHIVE` in
   `launcher.py` so the new bundle restores on next launch.)
3. Re-run `build.bat`.

---

## Antivirus / SmartScreen

PyInstaller bootloaders are routinely flagged by Defender heuristics.
Mitigations baked in:

- `upx=False` in `osint.spec` (UPX-packed binaries are the worst
  offenders)
- `--clean` in `build.bat`
- Hidden-import collection done via `collect_all` + explicit lists, not
  bytecode patching

For a public release you should additionally:

1. Code-sign `OSINT.exe` and the installer with an OV or EV cert.
2. Submit the signed binary to
   [Microsoft Defender for review](https://www.microsoft.com/en-us/wdsi/filesubmission)
   so SmartScreen learns to trust it.
3. Keep the installer URL stable — SmartScreen reputation is per-URL.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `OSINT.exe` exits immediately, no window | Crash before logging set up | Check `%LOCALAPPDATA%\OSINT\logs\crash.log` |
| "Elasticsearch failed to start" dialog | AV quarantined `elasticsearch\bin\java.exe`, port 9200 firewalled, or corrupted install | Whitelist the install dir; check `es.err.log` |
| Snapshot restore loops every launch | `_restore` returned an error (often a permissions issue on `path.repo`) | Inspect `launcher.log`; manually delete `.firstrun_done` after fixing |
| `/_next/static/...` 404s in browser | Frontend not exported, or static dir not bundled | Re-run `build.bat`; verify `backend\app\static\_next\` exists in `dist\OSINT\_internal\app\static\_next\` |
| Build fails with "collect_all(reportlab) failed" | Missing native dep | `pip install -U reportlab` inside `.buildvenv\` and re-run |
| Two `OSINT.exe` icons in taskbar | Single-instance check failed (rare) | Reboot — stale named mutex |

---

## What this packaging does NOT change

- `backend/app/` — every file untouched
- `frontend/app/` — every file untouched
- API contract, SSE endpoints, scoring logic, OSINT pipeline, exports —
  all unchanged
- `frontend/next.config.mjs` — the only edit; gated behind
  `NEXT_OUTPUT_EXPORT=1`. Dev behaviour (`npm run dev`) is identical
  to before.

If you need to revert the static export and run the dev frontend again,
restore `backend/app/.static.backup` over `backend/app/static`.
