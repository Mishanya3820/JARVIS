# PyInstaller spec for the local JARVIS GUI.
# Models and resources stay outside the executable so they can live beside it.
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules, collect_dynamic_libs


# Several TTS dependencies (notably trainer) contain package-level files
# such as VERSION that are read directly from disk at import time.
# collect_all() keeps Python modules and non-Python package data files.
packages = ["vosk", "TTS", "trainer"]

hiddenimports = []
datas = []
binaries = []

for package in packages:
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

hiddenimports += collect_submodules("customtkinter")
hiddenimports += ["sounddevice"]
datas += collect_data_files("customtkinter")
binaries += collect_dynamic_libs("TTS")


a = Analysis(
    ["Jarvis System/jarvis_gui.py"],
    pathex=["Jarvis System"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="JARVIS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="JARVIS",
)
