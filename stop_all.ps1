Set-Location -LiteralPath $PSScriptRoot

# Stop Stock Lab and clean up the retired standalone Streamlit UI if it is still running.
foreach ($port in 8787, 8501) {
  Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { Stop-Process -Id $_ -ErrorAction SilentlyContinue }
}
