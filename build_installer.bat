@echo off
setlocal
cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo Run start.bat once first so the virtual environment exists.
  pause
  exit /b 1
)

echo Installing PyInstaller...
"%PY%" -m pip install -q pyinstaller
if errorlevel 1 goto fail

echo Building CAUnpacker.exe ...
"%PY%" -m PyInstaller --noconfirm --clean CAUnpacker.spec
if errorlevel 1 goto fail

set "ISCC="
if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if defined ISCC (
  echo Building installer with Inno Setup...
  "%ISCC%" "installer\ca-unpacker.iss"
  if errorlevel 1 goto fail
  echo.
  echo Installer: dist\CAUnpacker-Setup.exe
) else (
  echo Inno Setup not found. Creating a portable zip instead.
  "%PY%" -c "import shutil; shutil.make_archive('dist/CAUnpacker-Portable', 'zip', 'dist/CAUnpacker')"
  echo Portable zip: dist\CAUnpacker-Portable.zip
)

echo Done.
exit /b 0

:fail
echo Build failed.
pause
exit /b 1
