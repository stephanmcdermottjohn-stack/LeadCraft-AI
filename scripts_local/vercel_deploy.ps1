# Deploys LeadCraft AI (backend or frontend) with the Vercel CLI.
# Auth: `npx vercel@latest login` (OAuth device flow) as a member of the
# `lead-generators` team. No token file is read, stored or printed.
# Usage: powershell -ExecutionPolicy Bypass -File scripts_local/vercel_deploy.ps1 -Which backend|frontend
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("backend", "frontend")]
    [string]$Which
)
# Native CLIs (npx/vercel) write progress and info to stderr. Under Windows
# PowerShell 5.1, `2>&1` turns that into an ErrorRecord, so "Stop" would abort a
# perfectly healthy call (e.g. `vercel teams ls`). Keep Continue and rely on the
# explicit $LASTEXITCODE checks below.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$scope = "lead-generators"

Push-Location $root
try {
    # Preflight: the CLI must be logged in and the team must be visible.
    $who = (npx --yes vercel@latest whoami 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        "Not logged in to Vercel. Run: npx --yes vercel@latest login"
        "Then sign in with the account that owns the '$scope' team."
        exit 1
    }
    "logged in as: $who"

    $teams = (npx --yes vercel@latest teams ls 2>&1 | Out-String)
    if ($teams -notmatch [regex]::Escape($scope)) {
        "Team '$scope' is not visible to this account."
        "Log out and log in again with the correct Vercel account: npx --yes vercel@latest logout; npx --yes vercel@latest login"
        exit 1
    }

    if ($Which -eq "backend") {
        $ignore = Join-Path $root "backend\.vercelignore"
        if (-not (Test-Path $ignore)) {
            "Missing backend\.vercelignore - refusing to deploy (it keeps .env, tests, DB and logs out of the build)."
            exit 1
        }
    }

    # The frontend project has Root Directory = frontend, so the CLI must run from
    # the repo root (Vercel then builds the frontend/ subfolder). The backend has no
    # Root Directory setting and is deployed from backend/.
    $dir = if ($Which -eq "frontend") { $root } else { Join-Path $root $Which }
    "deploying $Which from $dir ..."
    Push-Location $dir
    try {
        npx --yes vercel@latest deploy --prod --scope $scope --yes
        $code = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    exit $code
}
finally {
    Pop-Location
}
