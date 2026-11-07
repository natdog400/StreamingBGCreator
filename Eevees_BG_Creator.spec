# -*- mode: python ; coding: utf-8 -*-

# Build with:  pyinstaller Eevees_BG_Creator.spec
# Run from the repository root so the backgroundcreator package is importable.

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets',
        'PySide6.QtNetwork',
        'PySide6.QtSvg',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'altair',
        'cv2',
        'matplotlib',
        'numpy',
        'onnx',
        'pandas',
        'pygame',
        'scipy',
        'sklearn',
        'speech_recognition',
        'sympy',
        'tensorflow',
        'torch',
        'torchvision',
        'transformers',
    ],
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
    name='Eevees_BG_Creator',
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
)
