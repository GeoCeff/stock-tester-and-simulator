Set-Location -LiteralPath $PSScriptRoot
$existing = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existing) {
  Write-Host "Dashboard already running at http://127.0.0.1:8787 (PID $($existing.OwningProcess))."
  Start-Process "http://127.0.0.1:8787"
  return
}
node server.js
