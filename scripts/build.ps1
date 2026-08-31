$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
python -m pip install -r requirements.txt
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) { throw "Dependency installation failed with exit code $exitCode" }
$exe = Join-Path $root 'dist\Utthan-Society-Manager.exe'
if (Test-Path $exe) { Remove-Item $exe -Force }
python -m PyInstaller --noconfirm --clean --onefile --windowed --name "Utthan-Society-Manager" --manifest "app.manifest" --collect-all reportlab app.py
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) { throw "EXE build failed with exit code $exitCode" }
Write-Host "`nEXE created at: $exe" -ForegroundColor Green
