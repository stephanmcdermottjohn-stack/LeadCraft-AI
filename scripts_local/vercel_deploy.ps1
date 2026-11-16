# Deploys LeadCraft AI projects via REST API with path remapping.
# Backend project gets backend/* remapped to root (official FastAPI layout).
# Frontend project gets frontend/* remapped to root (Vite preset layout).
param([Parameter(Mandatory=$true)][string]$Which)
$ErrorActionPreference = "Stop"
Set-Location "E:\VirtualMarketingPlatform"

$token = Get-Content .vercel-token -Raw
$h = @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" }

$files = @()
foreach ($f in (git ls-files)) {
    if (-not (Test-Path $f)) { continue }
    if ($Which -eq "backend") {
        if (-not $f.StartsWith("backend/")) { continue }
        $dest = $f.Substring("backend/".Length)
    } else {
        if (-not ($f.StartsWith("frontend/") -or $f -eq ".gitignore")) { continue }
        $dest = if ($f.StartsWith("frontend/")) { $f.Substring("frontend/".Length) } else { $f }
    }
    $b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Resolve-Path $f).Path))
    $files += @{ file = $dest; data = $b64; encoding = "base64" }
}
"[$Which] uploading $($files.Count) files..."

$name = if ($Which -eq "backend") { "lead-craft-api" } else { "lead-craft-ai" }
$bodyObj = @{
    name   = $name
    target = "production"
    files  = $files
}
$body = ConvertTo-Json $bodyObj -Depth 5

try {
    $dep = Invoke-RestMethod -Method Post -Uri "https://api.vercel.com/v13/deployments" -Headers $h -Body $body
} catch {
    "deploy POST failed: $($_.ErrorDetails.Message)"
    exit 1
}

$depId = $dep.uid
"url: $($dep.url)"
"state: $($dep.readyState) - building..."

$deadline = (Get-Date).AddMinutes(10)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 10
    $deps = Invoke-RestMethod -Uri "https://api.vercel.com/v6/deployments?app=$name&limit=1&target=production" -Headers $h
    $d = $deps.deployments[0]
    if ($d.readyState -in @("READY", "ERROR", "CANCELED")) {
        "final state: $($d.readyState)"
        if ($d.readyState -ne "READY") {
            $logs = Invoke-RestMethod -Uri "https://api.vercel.com/v2/deployments/$($d.uid)/events?limit=60&builds=1" -Headers $h
            ($logs | ForEach-Object { $_.payload.text }) | Where-Object { $_ } | Select-Object -Last 30
        }
        exit
    }
}
"timeout waiting for deployment $depId"
