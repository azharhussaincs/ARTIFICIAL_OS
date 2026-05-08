# -*- mode: python ; coding: utf-8 -*-
# OSINT Platform — PyInstaller spec
#
# Build:    pyinstaller --noconfirm --clean osint.spec
# Outputs:  dist/OSINT/OSINT.exe + dist/OSINT/_internal/...
#
# This spec assumes it is invoked from the packaging/ directory.

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

HERE = Path(os.path.abspath(SPECPATH))
BACKEND = (HERE / ".." / "backend").resolve()

block_cipher = None

datas = []
binaries = []
hiddenimports = []

# ---- Bundle full Python packages we depend on ----------------------------
# collect_all returns (datas, binaries, hiddenimports) for a package and ALL
# of its submodules. This is the safest approach for libraries with dynamic
# imports (FastAPI, pydantic, elasticsearch, reportlab, lxml, PIL, ...).

_collect_packages = [
    # web stack
    "fastapi", "starlette", "uvicorn", "anyio", "sniffio",
    "h11", "httptools", "websockets", "watchfiles",
    # validation / settings
    "pydantic", "pydantic_core", "pydantic_settings",
    # http
    "httpx", "httpcore", "certifi", "idna",
    # database
    "sqlalchemy", "aiosqlite",
    # OSINT / scraping
    "bs4", "lxml", "tldextract", "phonenumbers",
    "email_validator", "dns",
    # exports
    "reportlab", "PIL",
    # rate limiting
    "slowapi", "limits",
    # elasticsearch
    "elasticsearch", "elastic_transport",
    # snapshot decompression
    "zstandard",
    # rich / file uploads
    "multipart",
]

for pkg in _collect_packages:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:
        print(f"[osint.spec] WARN: collect_all({pkg}) failed: {e}", file=sys.stderr)

# ---- Explicit hidden imports for things autodetect misses ----------------

hiddenimports += collect_submodules("uvicorn")
hiddenimports += [
    # uvicorn dynamic loaders
    "uvicorn.logging",
    "uvicorn.loops.auto", "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto", "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on", "uvicorn.lifespan.off",
    # Pydantic v2 dynamic decoders
    "pydantic.deprecated.decorator",
    # Async sqlite
    "aiosqlite",
    # asyncio fallbacks
    "asyncio",
    # tarfile zstd codec on 3.12+ (no-op on older Python; harmless)
    "tarfile",
]

# ---- Bundle the FastAPI application source + static frontend -------------
#
# The destination "app" puts backend/app/* under sys._MEIPASS/app/* at
# runtime. With pathex below, `from app.main import app` resolves cleanly.

datas += [
    (str(BACKEND / "app"), "app"),
]

# ---- Optional resources --------------------------------------------------

icon_path = HERE / "assets" / "osint.ico"
exe_icon = str(icon_path) if icon_path.exists() else None

# ---- Analysis / EXE / COLLECT --------------------------------------------

a = Analysis(
    [str(HERE / "launcher.py")],
    pathex=[str(BACKEND)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(HERE / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter", "test", "unittest", "pydoc", "setuptools",
        "pip", "wheel", "distutils",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OSINT",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                     # UPX trips antivirus heuristics; keep off
    console=False,                 # No terminal window — GUI mode
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=exe_icon,
    version=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="OSINT",
)
