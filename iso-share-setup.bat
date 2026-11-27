@echo off
rem One-time setup: create SMB share "ipmi_iso" for ISO files.
rem Run this file once - it will request administrator rights (UAC).

net share ipmi_iso >nul 2>&1
if %errorlevel%==0 (
    echo Share ipmi_iso already exists:
    net share ipmi_iso
    pause
    exit /b 0
)

rem Self-elevate if not admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator rights...
    powershell -NoProfile -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b 0
)

net share ipmi_iso="%~dp0iso_share" /grant:%USERNAME%,READ
echo.
if %errorlevel%==0 (
    echo OK: share created. BMC will read ISO files from:
    net share ipmi_iso
) else (
    echo FAILED to create share.
)
pause
