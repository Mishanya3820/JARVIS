@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo        JARVIS - EXE BUILD
echo ========================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv not found.
    echo Create the virtual environment and install requirements first.
    pause
    exit /b 1
)

if not exist "JARVIS.spec" (
    echo [ERROR] JARVIS.spec not found.
    pause
    exit /b 1
)

echo [1/2] Checking PyInstaller...
.venv\Scripts\python.exe -m PyInstaller --version
if errorlevel 1 (
    echo [ERROR] PyInstaller is not installed in .venv.
    echo Run: .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo.
echo [2/2] Building JARVIS.exe...
.venv\Scripts\python.exe -m PyInstaller JARVIS.spec --clean --noconfirm
if errorlevel 1 (
    echo.
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
echo ========================================
echo BUILD COMPLETE
echo ========================================
echo.
echo Executable:
dist\JARVIS\JARVIS.exe
echo.
echo Keep the resources folder and Models folder next to the JARVIS folder.
echo XTTS will download its model automatically into Models\TTS.
echo.
pause
