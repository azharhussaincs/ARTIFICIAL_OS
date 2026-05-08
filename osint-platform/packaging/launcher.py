"""OSINT Platform — Windows desktop supervisor.

Spawned by OSINT.exe (PyInstaller --windowed). Responsibilities:

  1.  Single-instance lock (named mutex on Windows, fcntl elsewhere)
  2.  Free-port allocation for Elasticsearch + FastAPI
  3.  Spawn bundled Elasticsearch with bundled JDK, hidden console
  4.  Wait for ES cluster to reach yellow status
  5.  First-run snapshot restore (zstd-compressed tarball -> path.repo)
  6.  Inject runtime config via os.environ for the existing FastAPI app
  7.  Augment the FastAPI app with /_next + catch-all static routes so the
      Next.js export served from app/static/ works without any backend
      code change
  8.  Launch user's default browser to the API origin
  9.  Run uvicorn in the foreground (blocks)
 10.  Clean shutdown of Elasticsearch on exit (signal, atexit, finally)

The existing backend (osint-platform/backend/app) is NOT modified. All
runtime configuration is injected via environment variables BEFORE
`app.main` is imported, so the existing pydantic-settings loader picks
them up unchanged.
"""
from __future__ import annotations

import atexit
import ctypes
import json
import logging
import logging.handlers
import os
import signal
import socket
import subprocess
import sys
import tarfile
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
from contextlib import closing
from pathlib import Path
from typing import Optional

IS_FROZEN = getattr(sys, "frozen", False)
IS_WINDOWS = os.name == "nt"

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def app_root() -> Path:
    """Folder containing OSINT.exe (frozen) or packaging/ (dev)."""
    if IS_FROZEN:
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


ROOT = app_root()
ES_HOME = ROOT / "elasticsearch"
SNAPSHOT_ARCHIVE = ROOT / "es-snapshot" / "snap_v1.tar.zst"
PORTABLE_FLAG = ROOT / "portable.flag"


def resolve_userdata() -> Path:
    """Per-user, writable runtime directory.

    Portable mode: triggered by ``portable.flag`` next to the .exe; userdata
    sits inside the install folder so the entire app remains relocatable.

    Installed mode: ``%LOCALAPPDATA%\\OSINT`` (survives uninstall + update).
    """
    if PORTABLE_FLAG.exists():
        return ROOT / "userdata"
    if IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            base = str(Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "OSINT"


USERDATA = resolve_userdata()
ES_DATA = USERDATA / "es-data"
ES_LOGS = USERDATA / "es-logs"
ES_TMP = USERDATA / "es-tmp"
ES_REPO = USERDATA / "es-repo"
SQLITE_DIR = USERDATA / "sqlite"
LOG_DIR = USERDATA / "logs"
EXPORT_DIR = USERDATA / "exports"
FIRSTRUN = USERDATA / ".firstrun_done"
LOCK_FILE = USERDATA / "app.lock"

for _p in (ES_DATA, ES_LOGS, ES_TMP, ES_REPO, SQLITE_DIR, LOG_DIR, EXPORT_DIR):
    _p.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Logging + crash handler
# ---------------------------------------------------------------------------

logger = logging.getLogger("osint.launcher")
logger.setLevel(logging.INFO)
_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

_fh = logging.handlers.RotatingFileHandler(
    LOG_DIR / "launcher.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
)
_fh.setFormatter(_fmt)
logger.addHandler(_fh)

if not IS_FROZEN:
    _sh = logging.StreamHandler()
    _sh.setFormatter(_fmt)
    logger.addHandler(_sh)


def _excepthook(exctype, value, tb):
    crash = LOG_DIR / "crash.log"
    with open(crash, "a", encoding="utf-8") as f:
        f.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        traceback.print_exception(exctype, value, tb, file=f)
    logger.error("Unhandled exception", exc_info=(exctype, value, tb))


sys.excepthook = _excepthook


def _show_message(text: str, title: str = "OSINT Platform", icon: int = 0x40) -> None:
    """Show a Windows MessageBox; on non-Windows, print to stderr."""
    if IS_WINDOWS:
        try:
            ctypes.windll.user32.MessageBoxW(0, text, title, icon)
            return
        except Exception:
            pass
    print(f"{title}: {text}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Single-instance lock
# ---------------------------------------------------------------------------

_mutex_handle = None
_lock_fp = None


def acquire_single_instance() -> bool:
    """Return True if this is the only running instance.

    Windows: named mutex (Global\\OSINT_PLATFORM_SINGLETON).
    Other:   fcntl flock on app.lock.
    """
    global _mutex_handle, _lock_fp
    if IS_WINDOWS:
        ERROR_ALREADY_EXISTS = 183
        kernel32 = ctypes.windll.kernel32
        kernel32.SetLastError(0)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p
        ]
        _mutex_handle = kernel32.CreateMutexW(
            None, 1, "Global\\OSINT_PLATFORM_SINGLETON"
        )
        last_error = kernel32.GetLastError()
        if last_error == ERROR_ALREADY_EXISTS:
            return False
        return _mutex_handle is not None and _mutex_handle != 0
    try:
        import fcntl
        _lock_fp = open(LOCK_FILE, "w")
        fcntl.flock(_lock_fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Port allocation
# ---------------------------------------------------------------------------

def free_port(preferred: int) -> int:
    """Return ``preferred`` if free; otherwise an OS-assigned ephemeral port."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            pass
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s2:
        s2.bind(("127.0.0.1", 0))
        return s2.getsockname()[1]


# ---------------------------------------------------------------------------
# Elasticsearch heap sizing
# ---------------------------------------------------------------------------

def total_ram_bytes() -> int:
    if IS_WINDOWS:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return int(stat.ullTotalPhys)
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, ValueError):
        return 8 * 1024 ** 3


def es_heap_mb() -> int:
    """Cap heap at 25% of physical RAM, clamped to [1024MB, 4096MB].

    Desktop apps share RAM with the user's other workloads — we deliberately
    avoid the ES default of 50%. Below 4GB the JVM gets compressed-OOPs which
    is more cache-efficient anyway.
    """
    gb = total_ram_bytes() / (1024 ** 3)
    target = int(gb * 1024 * 0.25)
    return max(1024, min(target, 4096))


# ---------------------------------------------------------------------------
# Elasticsearch lifecycle
# ---------------------------------------------------------------------------

ES_PROC: Optional[subprocess.Popen] = None
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200


def start_elasticsearch(port: int) -> subprocess.Popen:
    env = os.environ.copy()
    env["ES_JAVA_HOME"] = str(ES_HOME / "jdk")
    env["ES_PATH_CONF"] = str(ES_HOME / "config")
    env["ES_TMPDIR"] = str(ES_TMP)
    heap = es_heap_mb()
    env["ES_JAVA_OPTS"] = (
        f"-Xms{heap}m -Xmx{heap}m -Djava.io.tmpdir=\"{ES_TMP}\""
    )

    bin_name = "elasticsearch.bat" if IS_WINDOWS else "elasticsearch"
    bin_path = ES_HOME / "bin" / bin_name

    args = [
        str(bin_path),
        f"-Ehttp.port={port}",
        f"-Epath.data={ES_DATA}",
        f"-Epath.logs={ES_LOGS}",
        f"-Epath.repo={ES_REPO}",
        "-Ediscovery.type=single-node",
        "-Expack.security.enabled=false",
        "-Enetwork.host=127.0.0.1",
        "-Eaction.destructive_requires_name=true",
    ]

    flags = (CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP) if IS_WINDOWS else 0

    out = open(LOG_DIR / "es.out.log", "ab", buffering=0)
    err = open(LOG_DIR / "es.err.log", "ab", buffering=0)
    logger.info("Starting Elasticsearch on 127.0.0.1:%d (heap=%dMB)", port, heap)
    return subprocess.Popen(
        args, env=env, stdout=out, stderr=err,
        stdin=subprocess.DEVNULL,
        creationflags=flags,
        cwd=str(ES_HOME),
    )


def wait_es_ready(port: int, timeout_s: int = 240) -> bool:
    deadline = time.time() + timeout_s
    url = (
        f"http://127.0.0.1:{port}/_cluster/health"
        f"?wait_for_status=yellow&timeout=5s"
    )
    while time.time() < deadline:
        if ES_PROC is not None and ES_PROC.poll() is not None:
            logger.error("ES exited early with code %s", ES_PROC.returncode)
            return False
        try:
            with urllib.request.urlopen(url, timeout=6) as r:
                if r.status == 200:
                    body = json.loads(r.read())
                    logger.info("ES ready: status=%s", body.get("status"))
                    return True
        except (urllib.error.URLError, ConnectionError, socket.timeout, OSError):
            time.sleep(1)
    return False


def stop_elasticsearch() -> None:
    global ES_PROC
    if ES_PROC is None or ES_PROC.poll() is not None:
        return
    logger.info("Stopping Elasticsearch (pid=%d)", ES_PROC.pid)
    try:
        if IS_WINDOWS:
            try:
                ES_PROC.send_signal(signal.CTRL_BREAK_EVENT)
            except Exception:
                ES_PROC.terminate()
        else:
            ES_PROC.terminate()
        try:
            ES_PROC.wait(timeout=30)
        except subprocess.TimeoutExpired:
            logger.warning("ES did not exit cleanly; killing")
            ES_PROC.kill()
            try:
                ES_PROC.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
    except Exception:
        logger.exception("Error stopping ES")


atexit.register(stop_elasticsearch)


# ---------------------------------------------------------------------------
# First-run snapshot restore
# ---------------------------------------------------------------------------

def _http_json(url: str, body: dict | None = None,
               method: str = "GET", timeout: int = 60) -> bytes:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _extract_zstd_tar(archive: Path, dest: Path) -> None:
    """Stream-decompress a .tar.zst into ``dest``.

    Uses Python 3.12+ native zstd if available (``mode='r:zst'``); otherwise
    falls back to the ``zstandard`` library. The zstandard library MUST be
    bundled with the application — build.bat installs it.
    """
    try:
        with tarfile.open(archive, mode="r:zst") as tf:  # py>=3.12
            tf.extractall(dest)
            return
    except (tarfile.ReadError, ValueError, OSError):
        pass
    import zstandard as zstd  # type: ignore
    with open(archive, "rb") as fh:
        dctx = zstd.ZstdDecompressor()
        with dctx.stream_reader(fh) as reader:
            with tarfile.open(fileobj=reader, mode="r|") as tf:
                tf.extractall(dest)


def first_run_restore(es_port: int) -> None:
    if FIRSTRUN.exists():
        return
    if not SNAPSHOT_ARCHIVE.exists():
        logger.warning("No snapshot bundled at %s — running with empty index",
                       SNAPSHOT_ARCHIVE)
        FIRSTRUN.write_text("no-snapshot")
        return

    logger.info("First run: extracting snapshot %s -> %s",
                SNAPSHOT_ARCHIVE, ES_REPO)
    try:
        _extract_zstd_tar(SNAPSHOT_ARCHIVE, ES_REPO)
    except Exception:
        logger.exception("Snapshot extraction failed; continuing without restore")
        return

    base = f"http://127.0.0.1:{es_port}"
    try:
        _http_json(
            f"{base}/_snapshot/local_repo",
            {"type": "fs", "settings": {"location": str(ES_REPO)}},
            method="PUT",
        )
        logger.info("Snapshot repo registered")
        _http_json(
            f"{base}/_snapshot/local_repo/snap_v1/_restore"
            f"?wait_for_completion=true",
            {}, method="POST", timeout=3600,
        )
        logger.info("Snapshot restored OK")
        FIRSTRUN.write_text("ok")
    except Exception:
        logger.exception("Snapshot restore failed (will retry on next launch)")


# ---------------------------------------------------------------------------
# FastAPI runtime config + app augmentation
# ---------------------------------------------------------------------------

def _inject_env(api_port: int, es_port: int) -> None:
    """Push runtime config into os.environ BEFORE app.main is imported.

    This is how the existing pydantic-settings loader gets its values without
    any source-code change to backend/app.
    """
    os.environ["HOST"] = "127.0.0.1"
    os.environ["PORT"] = str(api_port)
    os.environ["APP_ENV"] = "production"
    os.environ["DEBUG"] = "false"
    os.environ["ES_ENABLED"] = "true"
    os.environ["ES_URL"] = f"http://127.0.0.1:{es_port}"
    os.environ["ES_USER"] = "elastic"
    os.environ["ES_PASSWORD"] = ""
    os.environ["ES_VERIFY_CERTS"] = "false"
    os.environ["ES_INDEX"] = os.environ.get("ES_INDEX", "tc_index")
    os.environ["DATABASE_URL"] = (
        f"sqlite+aiosqlite:///{(SQLITE_DIR / 'osint.db').as_posix()}"
    )
    os.environ["ALLOWED_ORIGINS"] = (
        f"http://127.0.0.1:{api_port},http://localhost:{api_port}"
    )


def _augment_app_with_static(app) -> None:
    """Mount Next.js export paths (/_next, root assets) without touching backend.

    The backend already mounts /assets and serves /. Next.js export references
    /_next/static/... which the backend doesn't know about. We add the missing
    mounts at runtime here. Routes registered AFTER the API routers can never
    shadow /api/*.
    """
    try:
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import FileResponse
    except Exception:
        logger.exception("FastAPI static helpers unavailable")
        return

    # Locate the static dir as bundled into the PyInstaller package.
    if IS_FROZEN:
        # PyInstaller --onedir places datas under sys._MEIPASS at runtime,
        # but datas added with target dir 'app' end up beside the .exe in
        # --onedir mode. Prefer _MEIPASS / 'app/static' first.
        candidates = [
            Path(getattr(sys, "_MEIPASS", "")) / "app" / "static",
            ROOT / "_internal" / "app" / "static",
            ROOT / "app" / "static",
        ]
    else:
        candidates = [
            Path(__file__).resolve().parent.parent / "backend" / "app" / "static",
        ]
    static_dir: Optional[Path] = next((c for c in candidates if c.exists()), None)
    if static_dir is None:
        logger.warning("Static dir not found in any of: %s", candidates)
        return

    next_dir = static_dir / "_next"
    if next_dir.exists():
        app.mount("/_next",
                  StaticFiles(directory=str(next_dir)),
                  name="next-static")
        logger.info("Mounted /_next -> %s", next_dir)

    # Catch-all SPA fallback: any unmatched non-/api path returns the file
    # if it exists under static/, else index.html. Registered LAST so /api
    # and previously-mounted routes win.
    from fastapi import Request  # noqa
    from starlette.responses import Response

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> Response:
        if full_path.startswith("api/"):
            # Should never reach here because /api/* is registered first,
            # but guard anyway.
            return Response(status_code=404)
        candidate = static_dir / full_path
        if candidate.is_file():
            return FileResponse(str(candidate))
        index = static_dir / "index.html"
        if index.is_file():
            return FileResponse(str(index))
        return Response(status_code=404)


def run_fastapi(api_port: int, es_port: int) -> None:
    _inject_env(api_port, es_port)

    # Make backend/ importable when running unfrozen (the .spec adds it to
    # pathex so this is a no-op in the bundled .exe).
    if not IS_FROZEN:
        backend = Path(__file__).resolve().parent.parent / "backend"
        if str(backend) not in sys.path:
            sys.path.insert(0, str(backend))

    import uvicorn
    from app.main import app  # noqa: E402  — env must be set first
    _augment_app_with_static(app)

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=api_port,
        log_config=None,
        access_log=False,
        lifespan="on",
        loop="asyncio",
        http="h11",
        ws="none",
    )
    server = uvicorn.Server(config)
    logger.info("FastAPI starting on 127.0.0.1:%d", api_port)
    server.run()


# ---------------------------------------------------------------------------
# Browser
# ---------------------------------------------------------------------------

def open_browser_async(api_port: int) -> None:
    def _later():
        time.sleep(1.5)  # uvicorn typically up within a second
        try:
            webbrowser.open(f"http://127.0.0.1:{api_port}/")
        except Exception:
            logger.exception("Could not open browser")
    threading.Thread(target=_later, daemon=True).start()


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

def install_signal_handlers() -> None:
    def _handler(signum, frame):  # noqa: ARG001
        logger.info("Received signal %s; shutting down", signum)
        stop_elasticsearch()
        os._exit(0)
    if IS_WINDOWS:
        for sig in ("SIGINT", "SIGBREAK", "SIGTERM"):
            try:
                signal.signal(getattr(signal, sig), _handler)
            except (AttributeError, ValueError, OSError):
                pass
    else:
        signal.signal(signal.SIGINT, _handler)
        signal.signal(signal.SIGTERM, _handler)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("OSINT launcher starting (frozen=%s, root=%s, userdata=%s)",
                IS_FROZEN, ROOT, USERDATA)

    if not acquire_single_instance():
        logger.info("Another instance is already running.")
        _show_message(
            "OSINT Platform is already running.\n\n"
            "Check your taskbar / browser tabs.",
            icon=0x40,
        )
        sys.exit(0)

    install_signal_handlers()

    es_port = free_port(9200)
    api_port = free_port(8000)
    logger.info("Allocated ports: ES=%d API=%d", es_port, api_port)

    global ES_PROC
    ES_PROC = start_elasticsearch(es_port)

    if not wait_es_ready(es_port, timeout_s=240):
        logger.error("Elasticsearch did not become ready in time")
        _show_message(
            "Elasticsearch failed to start.\n\n"
            f"Logs: {LOG_DIR}\n\n"
            "Common causes:\n"
            " - Antivirus quarantined elasticsearch\\bin\\java.exe\n"
            " - Corrupted install (reinstall app)\n"
            " - Port 9200 blocked by firewall",
            icon=0x10,
        )
        sys.exit(1)

    first_run_restore(es_port)
    open_browser_async(api_port)

    try:
        run_fastapi(api_port, es_port)
    except SystemExit:
        raise
    except Exception:
        logger.exception("FastAPI crashed")
        _show_message(
            f"OSINT backend crashed.\n\nLogs: {LOG_DIR}",
            icon=0x10,
        )
    finally:
        stop_elasticsearch()


if __name__ == "__main__":
    main()
