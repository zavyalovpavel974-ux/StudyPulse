param(
    [string]$TaskName = "StudyPulse Daily Report",
    [string]$Time = "23:30"
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot
$DailyScript = Join-Path $ProjectRoot "scripts\run_studypulse_daily.ps1"

function Write-ProgressLog {
    param([string]$Message)
    Write-Host ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message)
}

if (-not (Test-Path $DailyScript)) {
    throw "Daily script not found: $DailyScript"
}

Write-ProgressLog "Progress: prepare to register Windows daily task"
Write-ProgressLog "Progress: task name $TaskName"
Write-ProgressLog "Progress: run time $Time"
Write-ProgressLog "Progress: script $DailyScript"

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$DailyScript`"" `
    -WorkingDirectory $ProjectRoot

$Trigger = New-ScheduledTaskTrigger -Daily -At $Time
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -Compatibility Win8

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Principal $Principal `
    -Settings $Settings `
    -Description "Run StudyPulse daily pipeline and generate the latest report." `
    -Force | Out-Null

Write-ProgressLog "Progress: Windows daily task registered"
Write-ProgressLog "Progress: check it in Task Scheduler: $TaskName"
