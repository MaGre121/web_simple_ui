@echo off
setlocal

set "PYTHON=py -3"
where py >nul 2>nul
if errorlevel 1 set "PYTHON=python"

echo [1/2] Installing runtime and build dependencies...
%PYTHON% -m pip install -r requirements.txt -r requirements-build.txt
if errorlevel 1 exit /b 1

echo [2/2] Building MaximoAssetScanUI.exe ...
%PYTHON% -m PyInstaller --noconfirm --clean MaximoAssetScanUI.spec
if errorlevel 1 exit /b 1

echo.
echo Build complete:
echo   dist\MaximoAssetScanUI.exe
