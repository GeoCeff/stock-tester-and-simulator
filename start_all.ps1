$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (!(Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue)) {
  Start-Process -FilePath node -ArgumentList "server.js" -WorkingDirectory (Join-Path $PSScriptRoot "execution_dashboard") -WindowStyle Hidden
}

Start-Sleep -Seconds 2
Start-Process "http://127.0.0.1:8787"
