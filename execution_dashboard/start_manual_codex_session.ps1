Set-Location -LiteralPath $PSScriptRoot

$url = "http://127.0.0.1:8787"
$existing = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1

if (!$existing) {
  Start-Process -FilePath node -ArgumentList "server.js" -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
  Start-Sleep -Seconds 1
}

$health = Invoke-RestMethod -Uri "$url/api/health" -TimeoutSec 5
Start-Process $url

$runbook = Join-Path $PSScriptRoot "MANUAL_CODEX_OPERATOR.md"
$prompt = @"
Open $runbook.
Use the dashboard at $url.
Manual Codex mode only: do not add API-key automation, do not weaken live-order/full-auto safety gates, and do not place or transmit orders for me.
Help me operate the dashboard live: inspect the current bot pick, model/research status, quote freshness, technicals, news/trends when I ask, and give pass/reduce/reject guidance with reasons.
"@

$prompt | Set-Clipboard

Write-Host ""
Write-Host "Manual Codex session ready: $url"
Write-Host "Safe server live orders enabled: $($health.liveOrdersEnabled)"
Write-Host "Full auto enabled: $($health.fullAutoEnabled)"
Write-Host "OpenAI API research enabled: $($health.openAiEnabled)"
Write-Host ""
Write-Host "Codex starter prompt copied to clipboard:"
Write-Host $prompt
