# GATO installer. Run from the repo folder:  powershell -ExecutionPolicy Bypass -File install.ps1
# Idempotent: safe to re-run. Creates .venv next to this file and installs pinned requirements.
$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

function Find-Py311 {
    foreach ($c in @('py -3.11', 'python')) {
        try {
            $parts = $c.Split(' ')
            $v = & $parts[0] $parts[1..($parts.Length)] --version 2>&1
            if ("$v" -match 'Python 3\.11\.') { return $c }
        } catch {}
    }
    return $null
}

$py = Find-Py311
if (-not $py) {
    Write-Host 'Python 3.11 not found - installing via winget...'
    winget install --id Python.Python.3.11 -e --silent --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
    $py = Find-Py311
    if (-not $py) { throw 'Python 3.11 install failed. Install it from python.org (tick Add to PATH) and re-run.' }
}
Write-Host "Using: $py"

$venvPy = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    $parts = $py.Split(' ')
    & $parts[0] $parts[1..($parts.Length)] -m venv .venv
}
& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE -ne 0) { throw 'pip install failed (see output above).' }

& $venvPy -c "import win32gui, cv2, numpy, torch, ultralytics, webview, windows_capture; print('imports OK')"
if ($LASTEXITCODE -ne 0) { throw 'Import check failed.' }
Write-Host ''
Write-Host 'Done. Start the game (windowed 1024x768 / 1280x960 / 1440x1080), log in to the field, then double-click run.bat'
