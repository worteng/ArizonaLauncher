# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('index.html', '.'),
        ('lucide.min.js', '.'),
        ('fonts', 'fonts'),
        ('wallpapers', 'wallpapers'),
        ('configs.txt', '.'),
        ('moonloader.txt', '.'),
        ('others.txt', '.'),
        ('updatenews.txt', '.'),
        ('libraries.txt', '.'),
        ('presets', 'presets'),
        ('moonloader', 'moonloader'),
    ],
    hiddenimports=['webview', 'PyQt5', 'PyQt5.QtWidgets', 'PyQt5.QtCore', 'PyQt5.QtGui', 'pyzipper'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy', 'PyQt5.QtWebEngine', 'PyQt5.QtWebEngineWidgets', 'PyQt5.QtWebEngineCore', 'PyQt5.QtWebChannel', 'PyQt5.QtQuick', 'PyQt5.QtQml', 'PyQt5.QtQuickWidgets', 'PyQt5.QtPositioning', 'PyQt5.QtPrintSupport', 'PyQt5.QtSql', 'PyQt5.QtSvg', 'PyQt5.QtTest', 'PyQt5.QtBluetooth', 'PyQt5.QtNfc', 'PyQt5.QtMultimedia', 'PyQt5.QtSensors', 'PyQt5.QtSerialPort', 'PyQt5.Qt3D', 'PyQt5.QtDataVisualization', 'PyQt5.QtCharts', 'PyQt5.QtScxml', 'PyQt5.QtRemoteObjects'],
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [('O', None, 'OPTION'), ('O', None, 'OPTION')],
    exclude_binaries=True,
    name='ArizonaLauncher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    console=False,
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version.txt',
    uac_admin=True,
    icon=['icon.ico'],
    hide_console='hide-early',
    manifest='ArizonaLauncher.manifest',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,
    upx=True,
    upx_exclude=[],
    name='ArizonaLauncher',
)
