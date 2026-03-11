# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


project_root = Path(SPECPATH)

datas = [
    (str(project_root / "maximo" / "web" / "templates" / "index.html"), "maximo/web/templates"),
]

hiddenimports = sorted(
    set(
        collect_submodules("uvicorn")
        + collect_submodules("fastapi")
        + collect_submodules("starlette")
        + collect_submodules("anyio")
    )
)


a = Analysis(
    ["run_web.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["watchfiles", "uvloop"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MaximoAssetScanUI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
