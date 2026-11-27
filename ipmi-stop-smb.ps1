$log = 'D:\АЙСРОБОТИКС\сайт\IPMI\svc_stop.log'
"--- $(Get-Date -Format o) ---" | Out-File -Encoding utf8 $log
net stop srv2 /y 2>&1 | Out-File -Encoding utf8 -Append $log
"net stop srv2 exit=$LASTEXITCODE" | Out-File -Encoding utf8 -Append $log
net stop srvnet /y 2>&1 | Out-File -Encoding utf8 -Append $log
"net stop srvnet exit=$LASTEXITCODE" | Out-File -Encoding utf8 -Append $log
$l = Get-NetTCPConnection -LocalPort 445 -State Listen -ErrorAction SilentlyContinue
if ($l) { "445 still listening: pid $($l[0].OwningProcess)" | Out-File -Encoding utf8 -Append $log } else { "445 free" | Out-File -Encoding utf8 -Append $log }
