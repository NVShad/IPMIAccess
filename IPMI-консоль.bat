@echo off
cd /d "%~dp0"
title IPMI Web-KVM bridge - do not close this window

rem Load local settings: BMC_HOST, BMC_USER, BMC_PWD, optional PY
if exist config.bat call config.bat

rem If bridge is already running - just open the page
netstat -ano | findstr ":7100" | findstr /I "LISTENING" >nul
if %errorlevel%==0 (
    start "" "http://localhost:7100/ipmi.html"
    exit /b 0
)

if not defined PY set "PY=python"

rem Open the page 3 seconds after bridge start
start "" /min cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:7100/ipmi.html"

echo ============================================
echo   IPMI Web-KVM: http://localhost:7100/ipmi.html
echo   Close this window to stop the bridge.
echo ============================================
echo.

"%PY%" ipmi_server.py

echo.
echo Bridge stopped or failed.
pause
