$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot
$LogDir = Join-Path $ProjectRoot "logs"
$LogName = "studypulse_daily_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss")
$LogPath = Join-Path $LogDir $LogName

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

function Write-ProgressLog {
    param([string]$Message)
    Write-Host ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message)
}

Start-Transcript -Path $LogPath -Append | Out-Null

try {
    Write-ProgressLog "Progress: start StudyPulse daily pipeline"
    Set-Location $ProjectRoot
    Write-ProgressLog "Progress: project root $ProjectRoot"
    python (Join-Path $ProjectRoot "scripts\run_pipeline.py")
    Write-ProgressLog "Progress: StudyPulse daily pipeline completed"
    Write-ProgressLog "Progress: log file $LogPath"
}
catch {
    Write-ProgressLog ("Progress: StudyPulse daily pipeline failed - {0}" -f $_.Exception.Message)
    throw
}
finally {
    Stop-Transcript | Out-Null
}
