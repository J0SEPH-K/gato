[Console]::OutputEncoding=[Text.Encoding]::UTF8
$h=@{'x-gato-token'=(Get-Content 'C:\GatoSrc\_lan\.tok' -Raw).Trim()}
$t=[string](iwr -UseBasicParsing -Uri 'http://127.0.0.1:8787/log?since=0' -Headers $h -TimeoutSec 15).Content
$lines=$t -split "`r`n"
$lines | Where-Object { $_ -match '22:(4[5-9]|5[0-9])' } | Select-Object -First 60
"=== TOTALS ==="
"total=" + $lines.Count
"clicks=" + @($lines | Where-Object { $_.Contains('몹 클릭') }).Count
"discard=" + @($lines | Where-Object { $_.Contains('폐기') }).Count
"dummy=" + @($lines | Where-Object { $_.Contains('더미몹') }).Count
"revive=" + @($lines | Where-Object { $_.Contains('부활') }).Count
"battle=" + @($lines | Where-Object { $_.Contains('전투') }).Count
