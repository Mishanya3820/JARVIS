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

echo [1/3] Checking PyInstaller...
.venv\Scripts\python.exe -m PyInstaller --version
if errorlevel 1 (
    echo [ERROR] PyInstaller is not installed in .venv.
    echo Run: .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo.
echo [2/3] Building JARVIS.exe...
.venv\Scripts\python.exe -m PyInstaller JARVIS.spec --clean --noconfirm
if errorlevel 1 (
    echo.
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
echo [3/3] Copying external JARVIS resources...
if exist "resources" xcopy "resources" "dist\JARVIS\resources\" /E /I /Y /Q >nul
if exist "settings.json" copy /Y "settings.json" "dist\JARVIS\settings.json" >nul
if not exist "dist\JARVIS\Models\TTS" mkdir "dist\JARVIS\Models\TTS"

echo.
echo ========================================
echo BUILD COMPLETE
echo ========================================
echo.
echo Executable:
echo dist\JARVIS\JARVIS.exe
echo.
echo The complete JARVIS folder is ready to launch.
echo XTTS models will be downloaded automatically into:
echo dist\JARVIS\Models\TTS
echo.
pause
