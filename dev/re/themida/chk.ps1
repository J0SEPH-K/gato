$p='C:\re\dumps\Gersang.exe.dump'
$fs=[IO.File]::OpenRead($p)
$b=New-Object byte[] 512
$fs.Read($b,0,512) | Out-Null
$fs.Close()
'MZ=' + ($b[0..1] -join ',')
'lfanew=' + [BitConverter]::ToUInt32($b,0x3c)
'len=' + (Get-Item $p).Length
