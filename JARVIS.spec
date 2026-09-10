# PyInstaller spec for the local JARVIS GUI.
# Models and resources stay outside the executable so they can live beside it.
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs


hiddenimports = []
hiddenimports += collect_submodules("TTS")
hiddenimports += collect_submodules("customtkinter")
hiddenimports += ["sounddevice"]

datas = []
datas += collect_data_files("TTS")
datas += collect_data_files("customtkinter")

binaries = []
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
