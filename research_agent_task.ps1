param(
    [switch]$Run,
    [string]$TaskName = "Stock Research Agent"
)

$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot
$python = Join-Path $repo ".venv\Scripts\python.exe"
$agent = Join-Path $repo "run_research_agent.py"
$data = Join-Path $repo "execution_dashboard\data"

if (!(Test-Path -LiteralPath $python) -or !(Test-Path -LiteralPath $agent)) {
    throw "Create .venv and install requirements before registering the research agent."
}

if ($Run) {
    New-Item -ItemType Directory -Force -Path $data | Out-Null
    $process = Start-Process -FilePath $python `
        -ArgumentList @("-u", $agent) `
        -WorkingDirectory $repo `
        -RedirectStandardOutput (Join-Path $data "research_agent.log") `
        -RedirectStandardError (Join-Path $data "research_agent_error.log") `
        -Wait -PassThru -WindowStyle Hidden
    exit $process.ExitCode
}

$principalId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Run" `
    -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Daily -At "06:00"
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 4) `
    -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable -WakeToRun
$principal = New-ScheduledTaskPrincipal -UserId $principalId -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Description "Runs real-data stock research once daily at 06:00 local while signed in." `
    -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Output "Registered and started '$TaskName'."
