@echo off
rem ============================================================
rem  One-time setup so the BMC (192.168.1.30) can mount ISOs
rem  from this PC over SMB:
rem   1. firewall: allow TCP 445 only from the BMC address
rem   2. enable SMB1 server (BMC firmware 2015 needs it)
rem   3. disable mandatory SMB signing
rem  Revert everything with ipmi-smb-revert.bat
rem ============================================================
title IPMI SMB setup (admin)

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator rights...
    powershell -NoProfile -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b 0
)

echo [1/3] Firewall rule for BMC...
powershell -NoProfile -Command "if (-not (Get-NetFirewallRule -DisplayName 'IPMI-BMC-SMB' -ErrorAction SilentlyContinue)) { New-NetFirewallRule -DisplayName 'IPMI-BMC-SMB' -Direction Inbound -Protocol TCP -LocalPort 445 -RemoteAddress 192.168.1.30 -Action Allow | Out-Null; 'created' } else { 'already exists' }"

echo [2/3] Enabling SMB1 server...
powershell -NoProfile -Command "Enable-WindowsOptionalFeature -Online -FeatureName 'SMB1Protocol-Server' -All -NoRestart -ErrorAction SilentlyContinue | Out-Null; Set-SmbServerConfiguration -EnableSMB1Protocol $true -Force; 'done'"

echo [3/3] Relaxing SMB signing...
powershell -NoProfile -Command "Set-SmbServerConfiguration -RequireSecuritySignature $false -Force; 'done'"

echo.
echo ============================================================
echo  Setup complete. In the IPMI console page:
echo   1. type this PC's Windows password into the Password field
echo   2. click Save, then Mount
echo ============================================================
pause
