@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0.env" (
  for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%~dp0.env") do (
    call :load_env "%%A" "%%B"
  )
) else (
  echo No .env file found.
  echo Will use baked production Supabase from apps/config.json for perfect direct in-app auth.
  echo (This gives you the strict email/password flow with no browser needed.)
  echo Copy .env.example to .env ONLY if testing against local Supabase.
)

set "URLCHK=MISSING"
if defined SUPABASE_URL (
  set "URLCHK=PRODUCTION (from .env)"
  if not "%SUPABASE_URL:127.0.0.1=%"=="%SUPABASE_URL%" set "URLCHK=LOCALHOST (from .env)"
  if /i not "%SUPABASE_URL:localhost=%"=="%SUPABASE_URL%" set "URLCHK=LOCALHOST (from .env)"
) else (
  if exist "apps\config.json" (
    set "URLCHK=PRODUCTION (from apps/config.json)"
  ) else (
    set "URLCHK=MISSING (no .env and no config.json)"
  )
)
echo SUPABASE_URL: %URLCHK%

if defined SUPABASE_ANON_KEY (
  echo SUPABASE_ANON_KEY: PRESENT
) else (
  if exist "apps\config.json" (
    echo SUPABASE_ANON_KEY: PRESENT (from apps/config.json - Python will load it)
  ) else (
    echo SUPABASE_ANON_KEY: MISSING
  )
)

if defined CA_UNPACKER_AUTH_URL (
  echo CA_UNPACKER_AUTH_URL: PRESENT (legacy - no longer used for auth)
) else (
  if exist "apps\config.json" (
    echo CA_UNPACKER_AUTH_URL: PRESENT in config (legacy - ignored)
  ) else (
    echo CA_UNPACKER_AUTH_URL: MISSING (legacy)
  )
)

echo.
echo ================================================
echo   CA Unpacker - Direct In-App Supabase Auth
echo ================================================
echo Auth mode: STRICT in-app email/password (no browser redirect)
echo - Fresh users must sign up / log in before folder or firm setup.
echo - Uses production Supabase from apps/config.json (unless .env overrides).
echo.

if exist "%~dp0dist\CAUnpacker\tesseract\tesseract.exe" (
  set "CAUNPACKER_TESSERACT=%~dp0dist\CAUnpacker\tesseract\tesseract.exe"
)
set "PY=%~dp0.venv\Scripts\python.exe"
set "LOG=%~dp0start-log.txt"

echo %date% %time% launch >> "%LOG%"

if not exist "%PY%" (
  echo First-time setup. This can take a minute...
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python was not found. Install Python 3 from python.org and tick "Add python.exe to PATH".
    pause
    exit /b 1
  )
  python -m venv .venv
  if errorlevel 1 (
    echo Could not create a virtual environment.
    pause
    exit /b 1
  )
  "%PY%" -m pip install --upgrade pip
  "%PY%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Could not install the app libraries. See start-log.txt
    pause
    exit /b 1
  )
  echo.
  echo Setup complete.
  echo.
  echo === Perfect Auth Baked In ===
  echo - Direct Supabase connection (production keys from apps/config.json)
  echo - Strict in-app auth gate (email + password only)
  echo - No more automatic browser signup
  echo - You will be required to sign in before choosing your Excel folder
)

"%PY%" -c "import cryptography" >nul 2>nul
if errorlevel 1 (
  echo Installing missing libraries...
  "%PY%" -m pip install -r requirements.txt
)

echo.
echo Starting CA Unpacker...
echo (Strict in-app Supabase auth - sign up or log in with email/password first)
echo.
"%PY%" -m apps.desktop
if errorlevel 1 (
  echo The app closed with an error. See start-log.txt
  "%PY%" -m apps.desktop >> "%LOG%" 2>&1
  type "%LOG%"
  pause
)
goto :eof

:load_env
set "_k=%~1"
set "_v=%~2"
if not defined _k exit /b 0
setlocal EnableDelayedExpansion
set "k=!_k!"
set "v=!_v!"
if not defined k (
  endlocal
  exit /b 0
)
if "!k:~0,1!"=="#" (
  endlocal
  exit /b 0
)
for /f "tokens=* delims= " %%K in ("!k!") do set "k=%%K"
if defined v (
  for /f "tokens=* delims= " %%V in ("!v!") do set "v=%%V"
)
for /l %%I in (1,1,8) do (
  if defined k if "!k:~-1!"==" " set "k=!k:~0,-1!"
  if defined v if "!v:~-1!"==" " set "v=!v:~0,-1!"
)
if /i not "!k!"=="SUPABASE_URL" if /i not "!k!"=="SUPABASE_ANON_KEY" if /i not "!k!"=="CA_UNPACKER_AUTH_URL" (
  rem CA_UNPACKER_AUTH_URL is legacy (browser flow removed). Still allow override for compatibility.
  endlocal
  exit /b 0
)
if not defined k (
  endlocal
  exit /b 0
)
if defined v (
  for /f "delims=" %%V in ("!v!") do (
    for /f "delims=" %%K in ("!k!") do (
      endlocal
      set "%%K=%%V"
      exit /b 0
    )
  )
)
for /f "delims=" %%K in ("!k!") do (
  endlocal
  set "%%K="
)
exit /b 0
