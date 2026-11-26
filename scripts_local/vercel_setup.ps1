# One-time Vercel bootstrap for LeadCraft AI using the Vercel CLI (no token file).
# Auth: `npx vercel@latest login` as a member of the `lead-generators` team.
# Does: backend env vars (via vercel_env.ps1) + frontend VITE_API_BASE.
# Dashboard-only steps (cannot be done by this script): project root directory,
# deployment protection, domains.
# Usage: powershell -ExecutionPolicy Bypass -File scripts_local/vercel_setup.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$scope = "lead-generators"
$apiUrl = "https://lead-craft-api.vercel.app"

& (Join-Path $PSScriptRoot "vercel_env.ps1")
if ($LASTEXITCODE -ne 0) { exit 1 }

Push-Location (Join-Path $root "frontend")
try {
    $apiUrl | npx --yes vercel@latest env add VITE_API_BASE --environment production,preview --force --scope $scope 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        "frontend env VITE_API_BASE set"
    } else {
        "frontend env VITE_API_BASE failed"
        exit 1
    }
}
finally {
    Pop-Location
}

@"
Remaining dashboard-only steps:
  1. lead-craft-api + lead-craft-ai -> Settings -> General -> Root Directory: leave empty
     (each project is deployed from its own folder).
  2. Deployment Protection stays on; do not add Protection Bypass secrets.
  3. Domains: lead-craft-ai.vercel.app (frontend), lead-craft-api.vercel.app (API).
"@
