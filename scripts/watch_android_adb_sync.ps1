param(
    [string]$PackageName = "com.studypulse.android",
    [string]$RemoteDir = "",
    [string]$DestinationDir = "",
    [string]$AdbPath = "",
    [int]$IntervalSeconds = 60,
    [string]$StateFile = "",
    [switch]$Once
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot
$SyncScript = Join-Path $ScriptRoot "sync_android_json_adb.ps1"

function Write-ProgressLog {
    param([string]$Message)
    Write-Host ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message)
}

function Resolve-Adb {
    param([string]$ConfiguredPath)

    if ($ConfiguredPath -and (Test-Path -LiteralPath $ConfiguredPath)) {
        return (Resolve-Path -LiteralPath $ConfiguredPath).Path
    }

    if ($env:STUDYPULSE_ADB -and (Test-Path -LiteralPath $env:STUDYPULSE_ADB)) {
        return (Resolve-Path -LiteralPath $env:STUDYPULSE_ADB).Path
    }

    $command = Get-Command adb.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $defaultAdb = Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"
    if (Test-Path -LiteralPath $defaultAdb) {
        return $defaultAdb
    }

    return $null
}

function Read-State {
    param([string]$Path)

    if ($Path -and (Test-Path -LiteralPath $Path)) {
        try {
            return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
        } catch {
            Write-ProgressLog ("Progress: state file unreadable; recreate state - {0}" -f $_.Exception.Message)
        }
    }

    return [pscustomobject]@{
        connected = $false
        last_serial = ""
        last_remote = ""
        last_checked_at = ""
    }
}

function Save-State {
    param(
        [string]$Path,
        [object]$State
    )

    $dir = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    $State | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Get-DeviceSerials {
    param([string]$ResolvedAdb)

    try {
        $lines = & $ResolvedAdb devices 2>$null
    } catch {
        Write-ProgressLog ("Progress: adb devices failed - {0}" -f $_.Exception.Message)
        return @()
    }

    $serials = @()
    foreach ($line in $lines) {
        if ($line -match "^(\S+)\s+device$") {
            $serials += $Matches[1]
        }
    }
    return $serials
}

function Get-LatestRemoteJson {
    param(
        [string]$ResolvedAdb,
        [string]$Serial,
        [string]$SourceDir
    )

    try {
        $remoteList = & $ResolvedAdb -s $Serial shell "ls -t $SourceDir/android_usage*.json 2>/dev/null" 2>$null
    } catch {
        Write-ProgressLog ("Progress: adb shell list failed for $Serial - {0}" -f $_.Exception.Message)
        return ""
    }

    if ($LASTEXITCODE -ne 0 -or -not $remoteList) {
        return ""
    }

    $latest = ($remoteList | Where-Object { $_ -match "android_usage.*\.json" } | Select-Object -First 1)
    if ($latest) {
        return $latest.Trim()
    }
    return ""
}

if (-not $RemoteDir) {
    $RemoteDir = "/sdcard/Android/data/$PackageName/files/exports"
}

if (-not $DestinationDir) {
    $DestinationDir = Join-Path ([Environment]::GetFolderPath("Desktop")) ".json"
}

if (-not $StateFile) {
    $StateFile = Join-Path $ProjectRoot "data\android_adb_watch_state.json"
}

Write-ProgressLog "Progress: start Android ADB connection watcher"
Write-ProgressLog "Progress: interval seconds $IntervalSeconds"
Write-ProgressLog "Progress: remote dir $RemoteDir"
Write-ProgressLog "Progress: destination dir $DestinationDir"
Write-ProgressLog "Progress: state file $StateFile"

while ($true) {
    $ResolvedAdb = Resolve-Adb -ConfiguredPath $AdbPath
    $state = Read-State -Path $StateFile
    $now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

    if (-not $ResolvedAdb) {
        Write-ProgressLog "Progress: adb.exe not found; watcher waiting"
        $state.connected = $false
        $state.last_checked_at = $now
        Save-State -Path $StateFile -State $state
        if ($Once) { exit 0 }
        Start-Sleep -Seconds $IntervalSeconds
        continue
    }

    $serials = @(Get-DeviceSerials -ResolvedAdb $ResolvedAdb)
    if (-not $serials -or $serials.Count -eq 0) {
        Write-ProgressLog "Progress: no ADB device connected; watcher waiting"
        $state.connected = $false
        $state.last_checked_at = $now
        Save-State -Path $StateFile -State $state
        if ($Once) { exit 0 }
        Start-Sleep -Seconds $IntervalSeconds
        continue
    }

    $serial = [string]$serials[0]
    $latestRemote = Get-LatestRemoteJson -ResolvedAdb $ResolvedAdb -Serial $serial -SourceDir $RemoteDir
    if (-not $latestRemote) {
        Write-ProgressLog "Progress: device connected but no Android JSON export found on $serial"
        $state.connected = $true
        $state.last_serial = $serial
        $state.last_checked_at = $now
        Save-State -Path $StateFile -State $state
        if ($Once) { exit 0 }
        Start-Sleep -Seconds $IntervalSeconds
        continue
    }

    $shouldSync = (-not $state.connected) -or ($state.last_serial -ne $serial) -or ($state.last_remote -ne $latestRemote)
    if ($shouldSync) {
        Write-ProgressLog "Progress: ADB device detected or new JSON found; sync once"
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $SyncScript `
            -PackageName $PackageName `
            -RemoteDir $RemoteDir `
            -DestinationDir $DestinationDir `
            -AdbPath $ResolvedAdb `
            -DeviceSerial $serial
        if ($LASTEXITCODE -eq 0) {
            $state.connected = $true
            $state.last_serial = $serial
            $state.last_remote = $latestRemote
            $state.last_checked_at = $now
            Save-State -Path $StateFile -State $state
        } else {
            Write-ProgressLog ("Progress: sync script exited with code {0}" -f $LASTEXITCODE)
        }
    } else {
        Write-ProgressLog "Progress: ADB device connected; no new Android JSON to sync"
        $state.connected = $true
        $state.last_serial = $serial
        $state.last_checked_at = $now
        Save-State -Path $StateFile -State $state
    }

    if ($Once) {
        exit 0
    }
    Start-Sleep -Seconds $IntervalSeconds
}
