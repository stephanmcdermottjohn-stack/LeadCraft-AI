# Sets LeadCraft AI backend env vars on Vercel (production + preview) with the Vercel CLI.
# Values are read from backend/.env and piped through stdin - never printed and never
# passed on the command line. Auth: `npx vercel@latest login` (team: lead-generators).
# Usage: powershell -ExecutionPolicy Bypass -File scripts_local/vercel_env.ps1 [-RotateSecretKey] [-DryRun]
#   -RotateSecretKey  generate a fresh 64-char SECRET_KEY (logs every user out)
#   -DryRun           only list the keys that would be set
param(
    [switch]$RotateSecretKey,
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$scope = "lead-generators"
$envFile = Join-Path $backend ".env"

if (-not (Test-Path $envFile)) {
    "backend\.env not found - nothing to read."
    exit 1
}

# Read backend/.env key=value pairs (values stay in memory).
$envMap = @{}
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)\s*$') { $envMap[$Matches[1]] = $Matches[2].Trim() }
}

if ($RotateSecretKey) {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $prodSecret = ([System.BitConverter]::ToString($bytes)).Replace("-", "").ToLower()
} else {
    $prodSecret = $envMap["SECRET_KEY"]
}

$vars = [ordered]@{
    DATABASE_URL          = $envMap["DATABASE_URL"]
    SECRET_KEY            = $prodSecret
    ENVIRONMENT           = "production"
    LLM_PROVIDER          = "gemini"
    GEMINI_API_KEY        = $envMap["GEMINI_API_KEY"]
    GEMINI_MODEL          = $envMap["GEMINI_MODEL"]
    APP_DISABLE_SCHEDULER = "1"
    CORS_ORIGINS          = "https://lead-craft-ai.vercel.app"
}

$missing = @($vars.Keys | Where-Object { [string]::IsNullOrWhiteSpace([string]$vars[$_]) })
if ($missing.Count -gt 0) {
    "Refusing to run - missing/empty values for: $($missing -join ', ')"
    exit 1
}

if ($DryRun) {
    "Would set on lead-craft-api (production, preview):"
    $vars.Keys | ForEach-Object { "  $_" }
    exit 0
}

Push-Location $backend
try {
    $failed = 0
    foreach ($key in $vars.Keys) {
        $value = [string]$vars[$key]
        $value | npx --yes vercel@latest env add $key --environment production,preview --force --scope $scope 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            "OK   $key"
        } else {
            "FAIL $key"
            $failed++
        }
    }
    if ($failed -gt 0) {
        "$failed variable(s) failed to set."
        exit 1
    }
    "done - redeploy with: .\scripts_local\vercel_deploy.ps1 -Which backend"
}
finally {
    Pop-Location
}
