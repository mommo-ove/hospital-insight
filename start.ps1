param([int]$Port = 8000, [switch]$SkipBuild, [switch]$Install)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $Executable ($LASTEXITCODE)" }
}

if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
if ((Get-Command uv -ErrorAction SilentlyContinue)) {
    Invoke-Checked 'uv' @('sync', '--frozen')
} else {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        Invoke-Checked 'python' @('-m', 'venv', '.venv')
    }
    Invoke-Checked '.\.venv\Scripts\python.exe' @('-m', 'pip', 'install', '-r', 'requirements.txt')
}

if (-not $SkipBuild) {
    Push-Location -LiteralPath 'frontend'
    try {
        if ($Install -or -not (Test-Path -LiteralPath 'node_modules')) {
            Invoke-Checked 'npm.cmd' @('ci', '--no-audit', '--fetch-timeout=60000', '--fetch-retries=1')
        }
        Invoke-Checked 'npm.cmd' @('run', 'build')
    } finally { Pop-Location }
}
Write-Host "Hospital Insight: http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host 'Press Ctrl+C to stop. Configure the model in .env; the default is an offline demo.'
Invoke-Checked '.\.venv\Scripts\python.exe' @('-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', "$Port")

