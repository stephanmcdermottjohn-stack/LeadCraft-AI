# Configures the backend project (rootDirectory, env) + frontend env.
$ErrorActionPreference = "Stop"
Set-Location "E:\VirtualMarketingPlatform"

$token = Get-Content .vercel-token -Raw
$h = @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" }
$frontendId = "prj_xCLfLGn3VUQeYtmGk3fMtURVmy0R"
$backendId = "prj_xXvVvel33LHIYYkB6RtwxRRQKHJW"

$b = Invoke-RestMethod -Method Patch -Uri "https://api.vercel.com/v9/projects/$backendId" -Headers $h -Body '{"rootDirectory": "backend"}'
"backend: rootDirectory=$($b.rootDirectory) name=$($b.name)"

$envMap = @{}
Get-Content backend\.env | ForEach-Object {
    if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)\s*$') { $envMap[$Matches[1]] = $Matches[2].Trim() }
}
$bytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$prodSecret = [System.BitConverter]::ToString($bytes).Replace("-", "").ToLower()

$vars = @(
    @{ key = "DATABASE_URL";          value = $envMap["DATABASE_URL"];   target = @("production", "preview"); type = "encrypted" },
    @{ key = "SECRET_KEY";            value = $prodSecret;               target = @("production", "preview"); type = "encrypted" },
    @{ key = "ENVIRONMENT";           value = "production";              target = @("production", "preview"); type = "plain" },
    @{ key = "LLM_PROVIDER";          value = "gemini";                  target = @("production", "preview"); type = "plain" },
    @{ key = "GEMINI_API_KEY";        value = $envMap["GEMINI_API_KEY"]; target = @("production", "preview"); type = "encrypted" },
    @{ key = "GEMINI_MODEL";          value = $envMap["GEMINI_MODEL"];   target = @("production", "preview"); type = "plain" },
    @{ key = "APP_DISABLE_SCHEDULER"; value = "1";                       target = @("production", "preview"); type = "plain" },
    @{ key = "CORS_ORIGINS";          value = "https://lead-craft-ai.vercel.app"; target = @("production", "preview"); type = "plain" }
)

$existing = Invoke-RestMethod -Uri "https://api.vercel.com/v9/projects/$backendId/env" -Headers $h
foreach ($k in ($existing.envs | ForEach-Object { $_.key }) | Select-Object -Unique) {
    if ($vars | Where-Object { $_.key -eq $k }) {
        try { Invoke-RestMethod -Method Delete -Uri "https://api.vercel.com/v9/projects/$backendId/env/$k" -Headers $h | Out-Null } catch {}
    }
}
$varBody = ConvertTo-Json @($vars) -Depth 5
$res = Invoke-RestMethod -Method Post -Uri "https://api.vercel.com/v10/projects/$backendId/env" -Headers $h -Body $varBody
"backend env created: $($res.created.Count)"

$feExisting = Invoke-RestMethod -Uri "https://api.vercel.com/v9/projects/$frontendId/env" -Headers $h
if ($feExisting.envs | Where-Object { $_.key -eq "VITE_API_BASE" }) {
    try { Invoke-RestMethod -Method Delete -Uri "https://api.vercel.com/v9/projects/$frontendId/env/VITE_API_BASE" -Headers $h | Out-Null } catch {}
}
$feBody = ConvertTo-Json @{ key = "VITE_API_BASE"; value = "https://lead-craft-api.vercel.app"; target = @("production", "preview"); type = "plain" } -Depth 4
Invoke-RestMethod -Method Post -Uri "https://api.vercel.com/v10/projects/$frontendId/env" -Headers $h -Body $feBody | Out-Null
"frontend env VITE_API_BASE set"
