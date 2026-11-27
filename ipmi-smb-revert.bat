@echo off
rem ============================================================
rem  Revert ipmi-smb-setup.bat changes:
rem   1. remove the BMC firewall rule
rem   2. disable SMB1 server
rem   3. restore mandatory SMB signing
rem ============================================================
title IPMI SMB revert (admin)

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator rights...
    powershell -NoProfile -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b 0
)

powershell -NoProfile -Command "Remove-NetFirewallRule -DisplayName 'IPMI-BMC-SMB' -ErrorAction SilentlyContinue; Set-SmbServerConfiguration -EnableSMB1Protocol $false -RequireSecuritySignature $true -Force; Disable-WindowsOptionalFeature -Online -FeatureName 'SMB1Protocol-Server' -NoRestart -ErrorAction SilentlyContinue | Out-Null; 'reverted'"

echo.
echo Done: SMB1 disabled, signing restored, firewall rule removed.
pause
