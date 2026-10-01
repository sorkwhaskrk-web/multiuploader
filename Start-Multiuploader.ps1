#Requires -Version 7.0
[CmdletBinding()]
param(
    [ValidateRange(1, 65535)][int]$Port = 8765,
    [switch]$EnablePublishing,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
if (-not $IsWindows) { throw 'This launcher requires Windows.' }
Push-Location -LiteralPath $PSScriptRoot
try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw 'uv is required. Install uv and restart PowerShell 7.'
    }
    # Skip editable-package build isolation; use the project's source directly.
    & uv sync --locked --no-install-project
    if ($LASTEXITCODE -ne 0) { throw 'Dependency setup failed.' }
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PYTHONPATH = Join-Path $PSScriptRoot 'src'
    $taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    $env:PATH = "$(Split-Path $taskPython);$env:PATH"
    $taskArgs = @('-m', 'shorts_distributor.web', '--port', "$Port")
    if ($EnablePublishing) { $taskArgs += '--allow-publish' }
    if (-not $NoBrowser) { $taskArgs += '--open' }
    & $taskPython @taskArgs
    exit $LASTEXITCODE
}
finally { Pop-Location }
