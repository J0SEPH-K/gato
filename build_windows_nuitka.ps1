# Builds dist-installer\GatoSetup.exe from a NUITKA-compiled build instead of PyInstaller.
# Nuitka turns the .py files into C and compiles them, so the shipped app carries no
# .pyc bytecode that could be decompiled back into readable source.
#   powershell -ExecutionPolicy Bypass -File build_windows_nuitka.ps1
# Needs: install.ps1 already run once (creates .venv), plus MSVC (the VS Build Tools).
$ErrorActionPreference = 'Continue'
Set-Location -Path $PSScriptRoot
$py = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { throw 'Run install.ps1 first (creates .venv).' }
$ProgressPreference = 'SilentlyContinue'

& $py -m pip install --upgrade nuitka ordered-set zstandard
if ($LASTEXITCODE -ne 0) { throw 'pip install nuitka failed' }

# Local modules that are imported lazily or by name; Nuitka's static analysis can miss those.
$mods = @('agf', 'autosupply', 'captcha', 'chat', 'remote_link', 'agent_link', 'update', 'second_pw',
          'sniffer', 'traders_ctl', 'watchdog', 'sprite_match', 'notify', 'net', 'dpi', 'wgc',
          'combat', 'detector', 'capture', 'input', 'vision', 'brain', 'prism', 'config', 'jochul')
$pkgs = @('ultralytics', 'torch', 'torchvision', 'scapy', 'websockets', 'cryptography', 'webview',
          'windows_capture', 'pythonnet', 'clr_loader', 'comtypes', 'uiautomation', 'win32com',
          'win32timezone', 'psutil', 'certifi', 'requests')

$nargs = @(
    '-m', 'nuitka',
    '--standalone',
    '--assume-yes-for-downloads',
    '--msvc=latest',
    '--windows-console-mode=disable',
    '--windows-uac-admin',
    '--windows-icon-from-ico=assets/app.ico',
    '--output-dir=distn',
    '--output-filename=Gato.exe',
    '--company-name=J0SEPH-K',
    '--product-name=GATO',
    '--include-data-dir=ui=ui',
    '--include-data-dir=assets=assets',
    '--include-data-file=settings.default.json=settings.default.json',
    '--include-data-file=VERSION=VERSION',
    '--nofollow-import-to=tkinter,matplotlib,pytest,IPython,notebook'
)
foreach ($m in $mods) { $nargs += "--include-module=$m" }
foreach ($p in $pkgs) { $nargs += "--include-package=$p" }
$nargs += 'run_gato.py'

Write-Host '== Nuitka =='
& $py @nargs
if ($LASTEXITCODE -ne 0) { throw 'Nuitka failed' }
if (-not (Test-Path 'distn\run_gato.dist\Gato.exe')) { throw 'distn\run_gato.dist\Gato.exe missing' }

Write-Host '== self-test of the compiled app =='
$st = Start-Process -FilePath 'distn\run_gato.dist\Gato.exe' -ArgumentList '--selftest' -Wait -PassThru
Get-Content "$env:LOCALAPPDATA\GATO\selftest.txt" -ErrorAction SilentlyContinue
if ($st.ExitCode -ne 0) { throw 'compiled self-test failed (see selftest.txt above)' }

# With Nuitka the .py files are compiled, so any copy left in the dist folder is only there for
# tracebacks. Drop them so the shipped tree contains no readable source.
Get-ChildItem 'distn\run_gato.dist' -Filter '*.py' -Recurse | Remove-Item -Force -ErrorAction SilentlyContinue

if (-not (Test-Path 'installer\vc_redist.x64.exe')) {
    Invoke-WebRequest 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile 'installer\vc_redist.x64.exe'
}
$iscc = @("$env:ProgramFiles\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", 'C:\InnoSetup\ISCC.exe') | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    Write-Host 'Installing Inno Setup...'
    Invoke-WebRequest 'https://github.com/jrsoftware/issrc/releases/download/is-6_7_4/innosetup-6.7.4.exe' -OutFile "$env:TEMP\innosetup.exe"
    Start-Process "$env:TEMP\innosetup.exe" -ArgumentList '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /DIR=C:\InnoSetup' -Wait
    $iscc = 'C:\InnoSetup\ISCC.exe'
}
Write-Host '== Inno Setup =='
$ver = (Get-Content 'VERSION' -ErrorAction SilentlyContinue | Select-Object -First 1)
if (-not $ver) { $ver = '1.0.0' }
# gato.iss packages ..\dist\Gato; a compiled build lands in distn\run_gato.dist.
New-Item -ItemType Directory -Force -Path 'dist' | Out-Null
if (Test-Path 'dist\Gato') { Remove-Item 'dist\Gato' -Recurse -Force }
Move-Item 'distn\run_gato.dist' 'dist\Gato'
& $iscc "/DAppVersion=$ver" 'installer\gato.iss'
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup failed' }
Get-Item 'dist-installer\GatoSetup.exe' | Select-Object FullName, @{n='MB';e={[math]::Round($_.Length/1MB)}}
