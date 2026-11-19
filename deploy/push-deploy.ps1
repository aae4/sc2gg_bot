param(
    [string]$VpsHost = $env:DEPLOY_HOST,
    [string]$RemoteScript = "/opt/sc2gg_bot/deploy/deploy.sh",
    [switch]$SkipPush
)

$ErrorActionPreference = "Stop"

# Fallback: read DEPLOY_HOST from gitignored .env if not passed via parameter or env var
if (-not $VpsHost -and (Test-Path ".env")) {
    $line = Get-Content ".env" | Where-Object { $_ -match '^\s*DEPLOY_HOST\s*=' } | Select-Object -First 1
    if ($line) {
        $VpsHost = ($line -split '=', 2)[1].Trim().Trim('"').Trim("'")
    }
}

if (-not $VpsHost) {
    throw "DEPLOY_HOST is not set. Pass -VpsHost <user@host> or add DEPLOY_HOST=<user@host> to .env (gitignored)."
}

if (-not $SkipPush) {
    Write-Host "==> Pushing local commits to origin..." -ForegroundColor Cyan
    git push
    if ($LASTEXITCODE -ne 0) {
        throw "git push failed"
    }
}

Write-Host "==> Deploying on $VpsHost..." -ForegroundColor Cyan
ssh $VpsHost "bash $RemoteScript"
if ($LASTEXITCODE -ne 0) {
    throw "Remote deploy failed with exit code $LASTEXITCODE"
}

Write-Host "==> Deploy finished." -ForegroundColor Green
