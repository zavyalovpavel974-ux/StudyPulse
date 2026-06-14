param(
    [string]$TaskName = "StudyPulse Android ADB Watch",
    [int]$IntervalSeconds = 60
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot
$WatchScript = Join-Path $ProjectRoot "scripts\watch_android_adb_sync.ps1"

function Write-ProgressLog {
    param([string]$Message)
    Write-Host ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message)
}

if (-not (Test-Path -LiteralPath $WatchScript)) {
    throw "Watch script not found: $WatchScript"
}

Write-ProgressLog "Progress: prepare to register Android ADB watcher task"
Write-ProgressLog "Progress: task name $TaskName"
Write-ProgressLog "Progress: interval seconds $IntervalSeconds"
Write-ProgressLog "Progress: script $WatchScript"

function Register-StartupFallback {
    param(
        [string]$ScriptPath,
        [int]$Interval
    )

    $StartupDir = [Environment]::GetFolderPath("Startup")
    $CmdPath = Join-Path $StartupDir "StudyPulse_Android_ADB_Watch.cmd"
    $LogDir = Join-Path $ProjectRoot "logs"
    $LogPath = Join-Path $LogDir "studypulse_adb_watch_startup.log"

    New-Item -ItemType Directory -Path $StartupDir -Force | Out-Null
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

    $Command = "@echo off`r`n"
    $Command += "cd /d `"$ProjectRoot`"`r`n"
    $Command += "start `"`" /min powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath`" -IntervalSeconds $Interval >> `"$LogPath`" 2>&1`r`n"
    Set-Content -LiteralPath $CmdPath -Value $Command -Encoding ASCII

    Write-ProgressLog "Progress: scheduled task registration was not available; startup fallback created"
    Write-ProgressLog "Progress: startup file $CmdPath"
    Write-ProgressLog "Progress: watcher will start after the next Windows login"
}

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$WatchScript`" -IntervalSeconds $IntervalSeconds" `
    -WorkingDirectory $ProjectRoot

$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable -Compatibility Win8

try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Principal $Principal `
        -Settings $Settings `
        -Description "Watch ADB device connection and sync latest StudyPulse Android JSON automatically." `
        -Force | Out-Null

    Write-ProgressLog "Progress: Android ADB watcher task registered"
    Write-ProgressLog "Progress: check it in Task Scheduler: $TaskName"
} catch {
    if ($_.Exception.Message -match "Access is denied|拒绝访问|权限") {
        Write-ProgressLog ("Progress: scheduled task registration denied - {0}" -f $_.Exception.Message)
        Register-StartupFallback -ScriptPath $WatchScript -Interval $IntervalSeconds
    } else {
        throw
    }
}
