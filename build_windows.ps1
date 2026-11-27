# Builds dist-installer\GatoSetup.exe (one-file installer) from this repo. Run in an ADMIN PowerShell:
#   powershell -ExecutionPolicy Bypass -File build_windows.ps1
# Needs: install.ps1 already run once (creates .venv). Downloads Inno Setup + the VC++ runtime if missing.
$ErrorActionPreference = 'Continue'   # native tools write progress to stderr; exit codes are checked explicitly
Set-Location -Path $PSScriptRoot
$py = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { throw 'Run install.ps1 first (creates .venv).' }
$ProgressPreference = 'SilentlyContinue'

& $py -m pip install --upgrade pyinstaller
if ($LASTEXITCODE -ne 0) { throw 'pip install pyinstaller failed' }

Write-Host '== PyInstaller =='
& $py -m PyInstaller gato.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
if (-not (Test-Path 'dist\Gato\Gato.exe')) { throw 'dist\Gato\Gato.exe missing' }

Write-Host '== self-test of the packaged app =='
$so = Join-Path $PWD 'selftest.stdout.txt'
$se = Join-Path $PWD 'selftest.stderr.txt'
$st = Start-Process -FilePath 'dist\Gato\Gato.exe' -ArgumentList '--selftest' -Wait -PassThru `
      -RedirectStandardOutput $so -RedirectStandardError $se
foreach ($p in @('dist\Gato\selftest.txt', "$env:LOCALAPPDATA\GATO\selftest.txt", $so, $se)) {
    if (Test-Path $p) { Write-Host "--- $p"; Get-Content $p -ErrorAction SilentlyContinue }
}
if ($st.ExitCode -ne 0) { throw 'packaged self-test failed (see selftest.txt above)' }

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
& $iscc "/DAppVersion=$ver" 'installer\gato.iss'
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup failed' }
Get-Item 'dist-installer\GatoSetup.exe' | Select-Object FullName, @{n='MB';e={[math]::Round($_.Length/1MB)}}
