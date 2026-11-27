# Revert ipmi-smb-guest.ps1 (and ipmi-smb-setup.bat firewall/SMB1 changes)
$ErrorActionPreference = 'Continue'
$log = "D:\АЙСРОБОТИКС\сайт\IPMI\ipmi-smb-guest.log"
function L($m) { $m | Out-File $log -Append -Encoding utf8 }
"=== ipmi-smb-revert $(Get-Date -Format s) ===" | Out-File $log -Append -Encoding utf8

# 1. Disable Guest account
$guest = Get-LocalUser | Where-Object { $_.SID.Value -like '*-501' }
if ($guest) { Disable-LocalUser -SID $guest.SID.Value; L 'guest disabled' }

# 2. LSA policies back to secure defaults
$lsa = 'HKLM:\SYSTEM\CurrentControlSet\Control\Lsa'
Set-ItemProperty $lsa -Name everyoneIncludesAnonymous -Value 0 -Type DWord
Set-ItemProperty $lsa -Name LimitBlankPasswordUse -Value 1 -Type DWord
L 'lsa restored'

# 3. LanmanServer null-session settings removed
$lsp = 'HKLM:\SYSTEM\CurrentControlSet\Services\LanmanServer\Parameters'
Set-ItemProperty $lsp -Name NullSessionShares -Value @() -Type MultiString
Set-ItemProperty $lsp -Name RestrictNullSessAccess -Value 1 -Type DWord
L 'null sessions closed'

# 4. Remove Everyone from the share ACL and NTFS
$everyone = (New-Object System.Security.Principal.SecurityIdentifier('S-1-1-0')).Translate([System.Security.Principal.NTAccount]).Value
Revoke-SmbShareAccess -Name 'ipmi_iso' -AccountName $everyone -Force -ErrorAction SilentlyContinue | Out-Null
$dir = (Get-SmbShare -Name 'ipmi_iso' -ErrorAction SilentlyContinue).Path
if ($dir) { icacls $dir /remove '*S-1-1-0' | Out-Null }
L 'Everyone access removed'

# 5. Firewall rule, SMB1, signing
Remove-NetFirewallRule -DisplayName 'IPMI-BMC-SMB' -ErrorAction SilentlyContinue
Set-SmbServerConfiguration -EnableSMB1Protocol $false -RequireSecuritySignature $true -Force -ErrorAction SilentlyContinue
Disable-WindowsOptionalFeature -Online -FeatureName 'SMB1Protocol-Server' -NoRestart -ErrorAction SilentlyContinue | Out-Null
L 'firewall rule removed, SMB1 disabled, signing restored'

# 6. Bring back the Windows SMB stack stopped for the Python SMB server
#    (kill ipmi_smb_server.py first if it is still running)
Get-Process -Name python -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*ipmi_smb_server*' } |
    Stop-Process -Force -ErrorAction SilentlyContinue
net start srvnet 2>&1 | Out-Null
net start srv2 2>&1 | Out-Null
Restart-Service lanmanserver -Force
L 'lanmanserver/srv2/srvnet restarted'
L 'DONE'
