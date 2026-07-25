Set-Location -LiteralPath $PSScriptRoot
$existing = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existing) {
  Write-Host "Port 8787 is already running (PID $($existing.OwningProcess)). Run .\stop_dashboard.ps1 first if you want to switch modes."
  Start-Process "http://127.0.0.1:8787"
  return
}
$env:ENABLE_LIVE_ORDERS = "1"
node server.js
