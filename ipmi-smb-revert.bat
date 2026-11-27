@echo off
rem ============================================================
rem  Revert ALL IPMI SMB changes:
rem   - disable Guest / anonymous access
rem   - remove Everyone from the share
rem   - remove the BMC firewall rule
rem   - disable SMB1, restore mandatory signing
rem ============================================================
title IPMI SMB revert (admin)

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator rights...
    powershell -NoProfile -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b 0
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ipmi-smb-revert.ps1"
echo.
echo Done: passwordless access removed, SMB1 disabled, signing
echo and firewall restored.
pause
