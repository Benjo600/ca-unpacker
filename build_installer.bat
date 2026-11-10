@echo off
setlocal
cd /d "%~dp0"

set "PY=C:\Users\Admin\AppData\Local\Programs\Python\Python313\python.exe"
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"

echo Using %PY%

for /f "delims=" %%v in ('call "%PY%" -c "from apps.version import APP_VERSION; print(APP_VERSION)"') do set "APP_VERSION=%%v"
if not defined APP_VERSION (
  echo Could not read APP_VERSION from apps.version. Refusing to build an unversioned installer.
  goto fail
)
echo App version %APP_VERSION%

"%PY%" -m pip install -q -r requirements.txt pyinstaller
if errorlevel 1 goto fail

echo Building CAUnpacker.exe ...
"%PY%" -m PyInstaller --noconfirm --clean CAUnpacker.spec
if errorlevel 1 goto fail

echo Bundling Tesseract if present...
"%PY%" installer\bundle_tesseract.py
if errorlevel 1 goto fail

echo Building CAUnpackerUpdater.exe ...
"%PY%" -m PyInstaller --noconfirm --clean CAUnpackerUpdater.spec
if errorlevel 1 goto fail
if not exist "dist\CAUnpackerUpdater.exe" (
  echo Updater helper was not built.
  goto fail
)
copy /y "dist\CAUnpackerUpdater.exe" "dist\CAUnpacker\CAUnpackerUpdater.exe" >nul
if errorlevel 1 goto fail

set "ISCC="
if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not defined ISCC (
  echo Inno Setup 6 not found. Install it from https://jrsoftware.org/isinfo.php
  goto fail
)

echo Building one-file installer...
"%ISCC%" /DAppVersion=%APP_VERSION% "installer\ca-unpacker.iss"
if errorlevel 1 goto fail

if exist "dist\CAUnpacker-Windows.zip" del /q "dist\CAUnpacker-Windows.zip"
"%PY%" -c "import zipfile; from pathlib import Path; z=Path('dist/CAUnpacker-Windows.zip'); src=Path('dist/CAUnpacker-Setup.exe');
zf=zipfile.ZipFile(z,'w',zipfile.ZIP_DEFLATED); zf.write(src, src.name); zf.close(); print('Wrote', z, 'size', z.stat().st_size)"

echo.
if exist "dist\CAUnpacker-Setup.exe" (
  copy /y "dist\CAUnpacker-Setup.exe" "designs\ca-unpacker-landing\CAUnpacker-Setup.exe" >nul
  echo Landing download file: designs\ca-unpacker-landing\CAUnpacker-Setup.exe
)
if exist "start.bat" (
  copy /y "start.bat" "designs\ca-unpacker-landing\start.bat" >nul
  echo Landing dev helper: designs\ca-unpacker-landing\start.bat
)
echo Give people the Setup exe (one file, double-click to install): dist\CAUnpacker-Setup.exe
echo Zip is optional: dist\CAUnpacker-Windows.zip
echo Inside it is one file: CAUnpacker-Setup.exe
They double-click Setup, then open CA Unpacker from the Start menu.
echo For source / developers: also copy start.bat to the landing folder.
exit /b 0

:fail
echo Build failed.
exit /b 1
