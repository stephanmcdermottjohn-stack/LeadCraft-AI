# Sets LeadCraft AI env vars on the Vercel project (production + preview).
# Token read from .vercel-token (gitignored). Secrets come from backend/.env.
$ErrorActionPreference = "Stop"
Set-Location "E:\VirtualMarketingPlatform"

$token = Get-Content .vercel-token -Raw
$projectId = "prj_xCLfLGn3VUQeYtmGk3fMtURVmy0R"

# Read backend/.env key=value pairs
$envMap = @{}
Get-Content backend\.env | ForEach-Object {
    if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)\s*$') { $envMap[$Matches[1]] = $Matches[2].Trim() }
}

# Production SECRET_KEY: rotate from the dev value (tokens are stateless HMAC;
# old local tokens stop working on prod — expected).
$bytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$prodSecret = [System.BitConverter]::ToString($bytes).Replace("-", "").ToLower()

$vars = @(
    @{ key = "DATABASE_URL";       value = $envMap["DATABASE_URL"];      target = @("production", "preview"); type = "encrypted" },
    @{ key = "SECRET_KEY";         value = $prodSecret;                  target = @("production", "preview"); type = "encrypted" },
    @{ key = "ENVIRONMENT";        value = "production";                 target = @("production", "preview"); type = "plain" },
    @{ key = "LLM_PROVIDER";       value = "gemini";                     target = @("production", "preview"); type = "plain" },
    @{ key = "GEMINI_API_KEY";     value = $envMap["GEMINI_API_KEY"];    target = @("production", "preview"); type = "encrypted" },
    @{ key = "GEMINI_MODEL";       value = $envMap["GEMINI_MODEL"];      target = @("production", "preview"); type = "plain" },
    @{ key = "APP_DISABLE_SCHEDULER"; value = "1";                       target = @("production", "preview"); type = "plain" }
)

$headers = @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" }

# Remove any existing vars with the same keys first (idempotent re-run)
$existing = Invoke-RestMethod -Uri "https://api.vercel.com/v9/projects/$projectId/env" -Headers $headers
foreach ($k in ($existing.envs | ForEach-Object { $_.key }) | Select-Object -Unique) {
    if ($vars | Where-Object { $_.key -eq $k }) {
        try { Invoke-RestMethod -Method Delete -Uri "https://api.vercel.com/v9/projects/$projectId/env/$k`?systemEnvironment=0" -Headers $headers | Out-Null } catch {}
    }
}

$body = ConvertTo-Json @($vars) -Depth 5
try {
    $res = Invoke-RestMethod -Method Post -Uri "https://api.vercel.com/v10/projects/$projectId/env" -Headers $headers -Body $body
    "created: $($res.created.Count)"
} catch {
    "create failed: $($_.ErrorDetails.Message)"
}
