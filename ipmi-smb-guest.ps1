# Enable passwordless (guest / null-session) access to the ipmi_iso share.
# Reverted by ipmi-smb-revert.ps1
$ErrorActionPreference = 'Continue'
$log = "D:\АЙСРОБОТИКС\сайт\IPMI\ipmi-smb-guest.log"
function L($m) { $m | Out-File $log -Append -Encoding utf8 }
"=== ipmi-smb-guest $(Get-Date -Format s) ===" | Out-File $log -Encoding utf8

# 1. Enable the Guest account (language-neutral: well-known SID *-501)
$guest = Get-LocalUser | Where-Object { $_.SID.Value -like '*-501' }
if ($guest) {
    Enable-LocalUser -SID $guest.SID.Value
    L "guest account '$($guest.Name)' enabled"
} else { L 'guest account not found' }

# 2. LSA policies: Everyone applies to anonymous users; blank-password
#    network logons allowed
$lsa = 'HKLM:\SYSTEM\CurrentControlSet\Control\Lsa'
Set-ItemProperty $lsa -Name everyoneIncludesAnonymous -Value 1 -Type DWord
Set-ItemProperty $lsa -Name LimitBlankPasswordUse -Value 0 -Type DWord
L 'lsa: everyoneIncludesAnonymous=1, LimitBlankPasswordUse=0'

# 3. LanmanServer: allow null-session access to ipmi_iso
$lsp = 'HKLM:\SYSTEM\CurrentControlSet\Services\LanmanServer\Parameters'
Set-ItemProperty $lsp -Name NullSessionShares -Value @('ipmi_iso') -Type MultiString
Set-ItemProperty $lsp -Name RestrictNullSessAccess -Value 0 -Type DWord
L 'lanmanserver: NullSessionShares=ipmi_iso, RestrictNullSessAccess=0'

# 4. Share ACL: Everyone = Read (language-neutral via SID translation)
$everyone = (New-Object System.Security.Principal.SecurityIdentifier('S-1-1-0')).Translate([System.Security.Principal.NTAccount]).Value
Grant-SmbShareAccess -Name 'ipmi_iso' -AccountName $everyone -AccessRight Read -Force | Out-Null
L "share acl: '$everyone' read"

# 5. NTFS ACL: Everyone = Read on the shared folder (path from the share itself)
$dir = (Get-SmbShare -Name 'ipmi_iso').Path
icacls $dir /grant '*S-1-1-0:(OI)(CI)R' | Out-Null
L "ntfs acl: Everyone read on $dir"

# 6. Restart the SMB server to apply everything
Restart-Service lanmanserver -Force
L 'lanmanserver restarted'
L 'DONE'
