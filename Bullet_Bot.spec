# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Bullet Bot (Flet + app package + context files).

Build (from project root, Windows):
  pyinstaller Bullet_Bot.spec

Requires: pip install pyinstaller
Optional: place icon.ico next to this spec for the .exe icon.

Do not bundle .env (secrets). Copy .env next to the built .exe or set env vars on the machine.
"""
import os

from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Data folders copied into the bundle (readable at runtime via sys._MEIPASS).
datas = [
    ("context", "context"),
]
_assets = os.path.join("app", "assets")
if os.path.isdir(_assets):
    datas.append((_assets, _assets))

binaries = []
hiddenimports = [
    "app",
    "app.database",
    "app.genai_service",
    "app.multimodal",
    "app.openai_org_usage",
    "bcrypt",
    "_cffi_backend",
]

# Pull in Flet runtime assets (required for packaged desktop apps).
_flet_datas, _flet_binaries, _flet_hidden = collect_all("flet")
datas += _flet_datas
binaries += _flet_binaries
hiddenimports += _flet_hidden


a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

_icon = "icon.ico" if os.path.isfile("icon.ico") else None

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Bullet Bot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
)
