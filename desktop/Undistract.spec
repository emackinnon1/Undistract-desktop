# -*- mode: python ; coding: utf-8 -*-

import os

# SPECPATH is the directory containing this spec file (i.e. desktop/)
# Project root is one level up from that
project_root = os.path.dirname(SPECPATH)
icon_path = os.path.join(project_root, 'logo.png')

a = Analysis(
    ['run_app.py'],
    pathex=[],
    binaries=[],
    datas=[(icon_path, '.')],
    hiddenimports=['undistract_desktop.blocklist_store', 'undistract_desktop.websocket_server'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Undistract',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[icon_path],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Undistract',
)
app = BUNDLE(
    coll,
    name='Undistract.app',
    icon=icon_path,
    bundle_identifier='com.undistract.desktop',
    info_plist={
        'NSBluetoothAlwaysUsageDescription': 'Undistract uses Bluetooth to connect to your blocking device to enforce website blocking.',
        'CFBundleName': 'Undistract',
        'CFBundleDisplayName': 'Undistract',
        'CFBundleShortVersionString': '0.1.0',
        'CFBundleVersion': '0.1.0',
        'LSMinimumSystemVersion': '10.15',
        'NSHighResolutionCapable': True,
    },
)
