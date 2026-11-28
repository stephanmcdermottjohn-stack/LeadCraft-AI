# Read-only production preflight for LeadCraft AI.
#
# Safe to run at any time: it only performs GETs, one anonymous event POST to a
# deliberately unknown page (which must be a silent 204), and the tracked-file
# secret scan. It never logs in, never creates a lead, never prints secrets.
#
# Usage (from the repo root):
#   powershell -ExecutionPolicy Bypass -File scripts_local\preflight_check.ps1
#   powershell -ExecutionPolicy Bypass -File scripts_local\preflight_check.ps1 -Slug my-business
#
# Exit code 0 = all checks passed; 1 = at least one failed.

param(
    [string]$ApiBase = "https://project-76ur0.vercel.app",
    [string]$FrontendBase = "https://lead-craft-ai.vercel.app",
    [string]$Slug = "",
    [switch]$SkipSecretScan
)

$ErrorActionPreference = "Continue"
$ApiBase = $ApiBase.TrimEnd("/")
$FrontendBase = $FrontendBase.TrimEnd("/")

if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) {
    Write-Host "FAIL: curl.exe not found (required for HTTP probes)." -ForegroundColor Red
    exit 1
}

$script:results = New-Object System.Collections.ArrayList

function Add-Result {
    param([string]$Name, [bool]$Ok, [string]$Detail = "")
    $null = $script:results.Add([pscustomobject]@{ Name = $Name; Ok = $Ok; Detail = $Detail })
}

function Get-HttpCode {
    param([string[]]$CurlArgs)
    $raw = & curl.exe -s -o NUL --max-time 25 -w "%{http_code}" @CurlArgs 2>$null
    if ($LASTEXITCODE -ne 0) { return "000" }
    return (($raw | Select-Object -Last 1) -as [string]).Trim()
}

function Test-Code {
    param([string]$Name, [string]$Expected, [string[]]$CurlArgs)
    $code = Get-HttpCode -CurlArgs $CurlArgs
    Add-Result -Name $Name -Ok ($code -eq $Expected) -Detail "expected $Expected, got $code"
}

# --- API -------------------------------------------------------------------
$healthRaw = & curl.exe -s --max-time 25 "$ApiBase/api/health" 2>$null
$healthOk = $false
$healthDetail = "no response"
if ($LASTEXITCODE -eq 0 -and $healthRaw) {
    try {
        $health = ($healthRaw | Out-String) | ConvertFrom-Json
        $healthOk = ($health.status -eq "ok")
        $healthDetail = "app=$($health.app) version=$($health.version) env=$($health.environment)"
    } catch {
        $healthDetail = "invalid JSON"
    }
}
Add-Result -Name "API health" -Ok $healthOk -Detail $healthDetail

Test-Code -Name "API protected leads -> 401" -Expected "401" -CurlArgs @("$ApiBase/api/leads")
Test-Code -Name "API protected pages -> 401" -Expected "401" -CurlArgs @("$ApiBase/api/pages")
Test-Code -Name "API protected analytics -> 401" -Expected "401" -CurlArgs @("$ApiBase/api/analytics/summary")

# Anonymous event to a page slug that must not exist: silent 204 by contract.
$tmp = Join-Path $env:TEMP "leadcraft_preflight_event.json"
try {
    [IO.File]::WriteAllText($tmp, '{"session_id":"session-smokecheck123","event":"page_view"}')
    $eventCode = Get-HttpCode -CurlArgs @(
        "-X", "POST",
        "-H", "Content-Type: application/json",
        "--data-binary", "@$tmp",
        "$ApiBase/api/public/pages/preflight-must-not-exist/events"
    )
    Add-Result -Name "Unknown page event -> 204" -Ok ($eventCode -eq "204") -Detail "expected 204, got $eventCode"
} finally {
    if (Test-Path $tmp) { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
}

# --- Frontend --------------------------------------------------------------
Test-Code -Name "Frontend root" -Expected "200" -CurlArgs @("$FrontendBase/")
Test-Code -Name "Frontend /p/ deep link" -Expected "200" -CurlArgs @("$FrontendBase/p/preflight-must-not-exist")
Test-Code -Name "Frontend /l/ deep link" -Expected "200" -CurlArgs @("$FrontendBase/l/preflight-must-not-exist")

if ($Slug) {
    $landingRaw = & curl.exe -s --max-time 25 "$ApiBase/api/public/landing/$Slug" 2>$null
    $landingOk = $false
    $landingDetail = "no response"
    if ($LASTEXITCODE -eq 0 -and $landingRaw) {
        try {
            $cfg = ($landingRaw | Out-String) | ConvertFrom-Json
            $landingOk = [bool]$cfg.business
            $landingDetail = if ($landingOk) { "business config present" } else { "missing business block" }
        } catch {
            $landingDetail = "invalid JSON"
        }
    }
    Add-Result -Name "Public landing config ($Slug)" -Ok $landingOk -Detail $landingDetail
}

# --- Repo hygiene ----------------------------------------------------------
if (-not $SkipSecretScan) {
    $scanner = Join-Path (Split-Path -Parent $PSScriptRoot) "scripts_local\check_secrets.ps1"
    if (Test-Path $scanner) {
        $scan = & powershell -ExecutionPolicy Bypass -File $scanner 2>&1
        $scanOk = ($LASTEXITCODE -eq 0) -and (($scan | Out-String) -match "PASS")
        Add-Result -Name "Tracked-file secret scan" -Ok $scanOk -Detail $(if ($scanOk) { "PASS" } else { "see scanner output" })
        if (-not $scanOk) { $scan | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkYellow } }
    } else {
        Add-Result -Name "Tracked-file secret scan" -Ok $false -Detail "scanner not found at $scanner"
    }
}

# --- Report ----------------------------------------------------------------
Write-Host ""
Write-Host "LeadCraft AI preflight" -ForegroundColor Cyan
Write-Host "  API:      $ApiBase"
Write-Host "  Frontend: $FrontendBase"
Write-Host ""

foreach ($r in $script:results) {
    if ($r.Ok) {
        Write-Host ("  PASS  {0,-38} {1}" -f $r.Name, $r.Detail) -ForegroundColor Green
    } else {
        Write-Host ("  FAIL  {0,-38} {1}" -f $r.Name, $r.Detail) -ForegroundColor Red
    }
}

$failed = @($script:results | Where-Object { -not $_.Ok }).Count
Write-Host ""
if ($failed -eq 0) {
    Write-Host "All $($script:results.Count) checks passed." -ForegroundColor Green
    exit 0
}
Write-Host "$failed of $($script:results.Count) checks failed." -ForegroundColor Red
exit 1
