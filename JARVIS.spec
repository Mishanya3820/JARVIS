# PyInstaller spec for the local JARVIS GUI.
# Models and resources stay outside the executable so they can live beside it.
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules, collect_dynamic_libs


# Vosk's Windows package explicitly calls os.add_dll_directory() on its
# own package directory during import. collect_all() keeps the package
# directory together with its DLLs, data and hidden imports so that the
# directory exists inside the PyInstaller runtime bundle.
vosk_datas, vosk_binaries, vosk_hiddenimports = collect_all("vosk")

tts_datas, tts_binaries, tts_hiddenimports = collect_all("TTS")

hiddenimports = []
hiddenimports += vosk_hiddenimports
hiddenimports += tts_hiddenimports
hiddenimports += collect_submodules("customtkinter")
hiddenimports += ["sounddevice"]

datas = []
datas += vosk_datas
datas += tts_datas
datas += collect_data_files("customtkinter")

binaries = []
binaries += vosk_binaries
binaries += tts_binaries
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
