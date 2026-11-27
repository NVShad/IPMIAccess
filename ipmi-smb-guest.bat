@echo off
rem ============================================================
rem  Allow PASSWORDLESS access to the ipmi_iso share so the BMC
rem  can mount ISOs without a Windows password:
rem   - enables Guest account and anonymous (null-session) access
rem   - grants Everyone read on the share and folder
rem  Note: port 445 is already open only for the BMC IP
rem  (firewall rule IPMI-BMC-SMB from ipmi-smb-setup.bat).
rem  Revert everything with ipmi-smb-revert.bat
rem ============================================================
title IPMI guest share setup (admin)

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator rights...
    powershell -NoProfile -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b 0
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ipmi-smb-guest.ps1"
type "%~dp0ipmi-smb-guest.log"
echo.
echo Done. The share ipmi_iso is now readable without a password.
pause
