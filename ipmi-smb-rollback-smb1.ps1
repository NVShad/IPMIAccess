# Roll back the pending SMB1 feature install and restart the SMB stack
$log = "D:\АЙСРОБОТИКС\сайт\IPMI\ipmi-smb-guest.log"
"=== smb1 rollback $(Get-Date -Format s) ===" | Out-File $log -Append -Encoding utf8
Disable-WindowsOptionalFeature -Online -FeatureName 'SMB1Protocol-Server' -NoRestart -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty RestartNeeded | Out-File $log -Append -Encoding utf8
Restart-Service lanmanserver -Force
'srv restarted' | Out-File $log -Append -Encoding utf8
'DONE' | Out-File $log -Append -Encoding utf8
