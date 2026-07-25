$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (!(Test-Path -LiteralPath $python)) {
  throw "Missing .venv. Run: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
}

if (!(Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue)) {
  Start-Process -FilePath node -ArgumentList "server.js" -WorkingDirectory (Join-Path $PSScriptRoot "execution_dashboard") -WindowStyle Hidden
}

if (!(Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue)) {
  Start-Process -FilePath $python -ArgumentList "-m", "streamlit", "run", "market_dashboard/dashboard.py", "--server.headless=true" -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
}

Start-Sleep -Seconds 2
Start-Process "http://127.0.0.1:8501"
Start-Process "http://127.0.0.1:8787"
