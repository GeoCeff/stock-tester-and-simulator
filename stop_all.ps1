Set-Location -LiteralPath $PSScriptRoot

foreach ($port in 8501, 8787) {
  Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { Stop-Process -Id $_ -ErrorAction SilentlyContinue }
}
