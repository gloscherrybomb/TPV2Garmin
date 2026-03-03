# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for TPV2Garmin — macOS .app bundle."""

import os

block_cipher = None

# Paths
SRC_DIR = os.path.join(os.path.dirname(SPEC), "..", "src")
ASSETS_DIR = os.path.join(SRC_DIR, "tpv2garmin", "assets")
ICON_FILE = os.path.join(ASSETS_DIR, "icon.icns")

a = Analysis(
    [os.path.join(SRC_DIR, "tpv2garmin", "app.py")],
    pathex=[SRC_DIR],
    binaries=[],
    datas=[
        (os.path.join(ASSETS_DIR, "icon.png"), os.path.join("tpv2garmin", "assets")),
    ],
    hiddenimports=[
        "pystray._darwin",
        "desktop_notifier",
        "rubicon.objc",
        "pyobjc_framework_Cocoa",
        "garth",
        "garth.sso",
        "garth.http",
        "garth.auth_tokens",
        "fit_file_faker",
        "fit_file_faker.fit_editor",
        "fit_file_faker.config",
        "fit_file_faker.utils",
        "fit_file_faker.vendor.fit_tool",
        "fit_file_faker.vendor.fit_tool.fit_file",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TPV2Garmin",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="TPV2Garmin",
)

app = BUNDLE(
    coll,
    name="TPV2Garmin.app",
    icon=ICON_FILE,
    bundle_identifier="com.tpv2garmin",
    info_plist={
        "NSPrincipalClass": "NSApplication",
        "NSHighResolutionCapable": True,
    },
)
