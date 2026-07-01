@echo off
title Electric Panel Manager v3

set "PY=python"
set "DIR=%~dp0"
set "PORT=8018"

:menu
cls
echo.
echo ==========================================
echo   Electric Management Panel v3
echo ==========================================
echo   Python: %PY%
echo   Port:   %PORT%
echo ==========================================
echo.
echo   --- Options ---
echo   1. Start Server
echo   2. Stop Server  
echo   3. Check Status
echo   4. Open Dashboard
echo   5. Exit
echo.
set "choice="
set /p "choice=  Select: "

if "%choice%"=="0" exit /b 0
if "%choice%"=="1" goto do_start
if "%choice%"=="2" goto do_stop
if "%choice%"=="3" goto do_status
if "%choice%"=="4" (start http://localhost:%PORT% & goto loop)
if "%choice%"=="5" exit /b 0
goto loop

:loop
goto menu

:do_start
"%PY%" -c "import urllib.request; r=urllib.request.urlopen('http://localhost:%PORT%/api/auth/users',timeout=3); exit(0)" 2>nul
if %ERRORLEVEL%==0 (
    echo   Already running! Use option 4 to open dashboard.
    pause
    goto loop
)
echo   Stopping old processes...
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM python3.exe >nul 2>&1
timeout /t 1 /nobreak >nul
echo   Starting server...
start "" /MIN cmd /c "cd /d "%CD%" && "%PY%" run.py --port %PORT%"
timeout /t 4 /nobreak >nul
"%PY%" -c "import urllib.request; r=urllib.request.urlopen('http://localhost:%PORT%/api/auth/users',timeout=3); exit(0)" 2>nul
if %ERRORLEVEL%==0 (
    echo   OK - Server is running.
    echo   Open: http://localhost:%PORT%
) else (
    echo   Failed. Check:
    echo     1. PostgreSQL service running?
    echo     2. pip install psycopg2-binary waitress
    echo     3. python --version
)
pause
goto loop

:do_stop
echo   Stopping server...
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM python3.exe >nul 2>&1
echo   Server stopped.
pause
goto loop

:do_status
echo.
"%PY%" -c "import urllib.request; r=urllib.request.urlopen('http://localhost:%PORT%/api/auth/users',timeout=3); exit(0)" 2>nul
if %ERRORLEVEL%==0 (
    echo   [Status] ONLINE - http://localhost:%PORT%
) else (
    echo   [Status] OFFLINE
)
echo.
pause
goto loop
