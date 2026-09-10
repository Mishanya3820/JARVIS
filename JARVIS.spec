# PyInstaller spec for the local JARVIS GUI.
# Heavy ML models stay outside the executable in the JARVIS folder.
from PyInstaller.utils.hooks import collect_all, collect_submodules


# These packages contain runtime-loaded modules and/or non-Python data files.
# collect_all() is intentionally used for the ML/audio stack to avoid the
# "works from Python, fails from EXE" class of packaging errors.
packages = [
    "vosk",
    "TTS",
    "trainer",
    "silero_vad",
    "sounddevice",
    "customtkinter",
]

hiddenimports = []
datas = []
binaries = []

for package in packages:
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

# Some TTS/VAD modules are imported dynamically.
hiddenimports += collect_submodules("TTS")
hiddenimports += collect_submodules("silero_vad")
hiddenimports += collect_submodules("customtkinter")

# Remove duplicate entries while preserving order.
def unique(items):
    return list(dict.fromkeys(items))


datas = unique(datas)
binaries = unique(binaries)
hiddenimports = unique(hiddenimports)


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
