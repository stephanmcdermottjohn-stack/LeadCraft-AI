# Scans git-tracked files for common secret patterns. Never prints values.
# Usage:  powershell -ExecutionPolicy Bypass -File scripts_local/check_secrets.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$patterns = @(
    @{ Name = "Google API key"; Regex = "AIza[0-9A-Za-z_-]{35}" },
    @{ Name = "Groq API key"; Regex = "gsk_[A-Za-z0-9]{20,}" },
    @{ Name = "OpenAI-style key"; Regex = "sk-[A-Za-z0-9_-]{20,}" },
    @{ Name = "Private key block"; Regex = "BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY" },
    @{ Name = "Postgres URL with password"; Regex = "postgres(ql)?://[A-Za-z0-9._-]+:[^@\s<>]+@" },
    @{ Name = "JWT token"; Regex = "eyJhbGciOi[A-Za-z0-9_-]{20,}" },
    @{ Name = "AWS access key"; Regex = "AKIA[0-9A-Z]{16}" },
    @{ Name = "GitHub token"; Regex = "gh[pousr]_[A-Za-z0-9]{30,}" },
    @{ Name = "Slack token"; Regex = "xox[abprs]-[A-Za-z0-9-]{10,}" }
)

$files = git ls-files
$hits = 0
foreach ($f in $files) {
    if (-not (Test-Path -LiteralPath $f)) { continue }
    if ($f -match "(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock)$") { continue }
    $text = Get-Content -Raw -LiteralPath $f -ErrorAction SilentlyContinue
    if ($null -eq $text) { continue }
    foreach ($p in $patterns) {
        $count = [regex]::Matches($text, $p.Regex).Count
        if ($count -gt 0) {
            $hits += $count
            "$($p.Name): $f ($count match(es))"
        }
    }
}

# Sensitive files must never be tracked.
foreach ($s in @(".env", "backend/.env", "frontend/.env", ".vercel-token")) {
    $tracked = @(git ls-files -- $s)
    if ($tracked.Count -gt 0) {
        $hits++
        "TRACKED SECRET FILE: $s"
    }
}

# Vercel deploys now use `vercel login`; a token file should no longer exist.
if (Test-Path ".vercel-token") {
    "NOTE: .vercel-token exists but is deprecated - deploys use `npx vercel@latest login` now. Delete the file."
}

if ($hits -gt 0) {
    "FAIL: $hits potential secret finding(s). Never commit these; rotate and remove them."
    exit 1
}

"PASS: no obvious secrets in tracked files; .env files are untracked and no Vercel token file is tracked."
exit 0
