@echo off
REM ============================================================================
REM  AI Crypto Tracker - Windows build script (PyInstaller)
REM  Mappas (onedir) buildet keszit, majd ha van Inno Setup, telepitot is.
REM
REM  Hasznalat:  dupla-katt a build.bat-ra, vagy parancssorbol:  build.bat
REM  Eredmeny:   dist\AI-Crypto-Tracker\AI-Crypto-Tracker.exe
REM              dist\AI-Crypto-Tracker-telepito.exe  (ha az Inno Setup 6 telepitve van)
REM ============================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

set "APP_NAME=AI-Crypto-Tracker"
set "ENTRY=ai-crypto-tracker.py"
set "REQ=requirements-ai-cripto-tracker.txt"
set "VENV=.build-venv"

echo.
echo === [1/6] Python ellenorzese ===
where py >nul 2>&1
if %errorlevel%==0 (
    set "PY=py -3"
) else (
    where python >nul 2>&1
    if %errorlevel%==0 (
        set "PY=python"
    ) else (
        echo [HIBA] Nem talalhato Python. Telepitsd: https://www.python.org/downloads/
        echo        A telepitesnel pipald be az "Add Python to PATH" opciot.
        pause
        exit /b 1
    )
)
%PY% --version

if not exist "%ENTRY%" (
    echo [HIBA] Nem talalom a fofajlt: %ENTRY%
    echo        Futtasd a build.bat-ot a projekt mappajabol.
    pause
    exit /b 1
)

echo.
echo === [2/6] Virtualis kornyezet (%VENV%) ===
if not exist "%VENV%\Scripts\python.exe" (
    %PY% -m venv "%VENV%"
    if errorlevel 1 (
        echo [HIBA] A venv letrehozasa sikertelen.
        pause
        exit /b 1
    )
)
set "VPY=%VENV%\Scripts\python.exe"

echo.
echo === [3/6] Fuggosegek telepitese ===
"%VPY%" -m pip install --upgrade pip
if exist "%REQ%" (
    "%VPY%" -m pip install -r "%REQ%"
) else (
    echo [info] %REQ% nem talalhato, kozvetlen telepites...
    "%VPY%" -m pip install requests numpy scikit-learn PySide6
)
"%VPY%" -m pip install --upgrade pyinstaller
if errorlevel 1 (
    echo [HIBA] A fuggosegek telepitese sikertelen.
    pause
    exit /b 1
)

echo.
echo === [4/6] Korabbi build torlese ===
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "%APP_NAME%.spec" del /q "%APP_NAME%.spec"

echo.
echo === [5/6] PyInstaller build ===
REM  --onedir      : mappas build, gyorsabban indul, ezt csomagolja a telepito
REM  --windowed    : ne nyiljon konzol-ablak (GUI app)
REM  --collect-*   : a scikit-learn rejtett moduljai/adatai kellenek futaskor
"%VPY%" -m PyInstaller ^
    --noconfirm ^
    --onedir ^
    --windowed ^
    --name "%APP_NAME%" ^
    --icon "assets\icon.ico" ^
    --add-data "assets;assets" ^
    --add-data "discordbot.zip;." ^
    --collect-submodules sklearn ^
    --collect-data sklearn ^
    --hidden-import sklearn.ensemble ^
    --hidden-import sklearn.tree ^
    --hidden-import sklearn.utils._typedefs ^
    --hidden-import sklearn.neighbors._partition_nodes ^
    "%ENTRY%"

if errorlevel 1 (
    echo.
    echo [HIBA] A build sikertelen. Nezd at a fenti uzeneteket.
    pause
    exit /b 1
)

echo.
echo === [6/6] Telepito (Inno Setup) ===
set "ISCC="
for %%I in (iscc.exe) do if not "%%~$PATH:I"=="" set "ISCC=%%~$PATH:I"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if defined ISCC (
    "%ISCC%" /Qp "windows\telepito.iss"
    if errorlevel 1 (
        echo [HIBA] A telepito forditasa sikertelen.
        pause
        exit /b 1
    )
) else (
    echo [info] Inno Setup 6 nem talalhato, telepito nem keszult.
    echo        Letoltes: https://jrsoftware.org/isdl.php  - utana futtasd ujra a build.bat-ot.
)

echo.
echo ============================================================================
echo  KESZ!  ->  dist\%APP_NAME%\%APP_NAME%.exe
if defined ISCC echo         dist\%APP_NAME%-telepito.exe
echo ============================================================================
echo.
pause
endlocal
