Set-Location -LiteralPath $PSScriptRoot
$listeners = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue
if (!$listeners) {
  Write-Host "Dashboard is not running on http://127.0.0.1:8787."
  return
}
$listeners | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
  Stop-Process -Id $_ -ErrorAction SilentlyContinue
  Write-Host "Stopped dashboard process $_."
}
