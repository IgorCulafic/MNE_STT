$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    Write-Host 'Create the virtual environment and install requirements first. See README.md.'
    exit 1
}
Write-Host 'Montenegrin STT Review: http://127.0.0.1:8769'
& $pythonPath run.py
