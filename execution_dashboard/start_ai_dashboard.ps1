Set-Location -LiteralPath $PSScriptRoot
$existing = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existing) {
  Write-Host "Dashboard already running at http://127.0.0.1:8787 (PID $($existing.OwningProcess)). Stop it first with stop_dashboard.ps1."
  return
}
if (!$env:OPENAI_API_KEY) {
  $secure = Read-Host "OpenAI API key for this session" -AsSecureString
  $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  try {
    $env:OPENAI_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
  } finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
  }
}
if (!$env:OPENAI_MODEL) {
  $env:OPENAI_MODEL = "gpt-5.4-mini"
}
node server.js
