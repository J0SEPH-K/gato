
[Console]::OutputEncoding=[Text.Encoding]::UTF8
$h=@{'x-gato-token'='mt4hjwtg3bj5pc4npa3o3w5rfgu4tk2c'}
$t=[string](iwr -UseBasicParsing -Uri 'http://127.0.0.1:8787/log?since=0' -Headers $h -TimeoutSec 20).Content
$lines=$t -split "`r`n"
"total=" + $lines.Count
"clicks=" + @($lines | Where-Object { $_.Contains('몹 클릭') }).Count
"discard=" + @($lines | Where-Object { $_.Contains('폐기') }).Count
"dummy=" + @($lines | Where-Object { $_.Contains('더미몹') }).Count
"revive=" + @($lines | Where-Object { $_.Contains('부활') }).Count
"blocked=" + @($lines | Where-Object { $_.Contains('막힘') }).Count
"--- last 25 non-gate ---"
$lines | Where-Object { -not $_.Contains('[게이트]') -and $_.Trim() -ne '' } | Select-Object -Last 25
