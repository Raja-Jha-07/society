$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed --name "Utthan-Society-Manager" --collect-all reportlab app.py
Write-Host "`nEXE created at: $root\dist\Utthan-Society-Manager.exe" -ForegroundColor Green
