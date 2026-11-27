@echo off
cd /d "%~dp0"
title IPMI ISO share server (port 445) - do not close this window

rem Load local settings (PY) if present
if exist config.bat call config.bat
if not defined PY set "PY=python"

rem Self-elevate: stopping the Windows SMB stack needs admin rights
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator rights...
    powershell -NoProfile -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b 0
)

echo Stopping Windows SMB services to free port 445...
net stop lanmanserver /y >nul 2>&1
net stop srv2 /y >nul 2>&1
net stop srvnet /y >nul 2>&1

echo ============================================
echo   ISO share: \\%COMPUTERNAME%\ipmi_iso
echo   Guest access, no password needed.
echo   Close this window to stop the server.
echo ============================================
echo.

"%PY%" ipmi_smb_server.py

echo.
echo SMB server stopped. To restore Windows file sharing run ipmi-smb-revert.bat
pause
