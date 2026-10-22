# -*- mode: python ; coding: utf-8 -*-
# 单文件版: 所有依赖打进一个 exe, 双击即用 (启动时会解压到临时目录, 首次启动稍慢)


a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('static', 'static'), ('samples', 'samples')],
    hiddenimports=['app'],
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
    a.binaries,
    a.datas,
    [],
    name='NaviVisionStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,
    icon='branding/app.ico',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
