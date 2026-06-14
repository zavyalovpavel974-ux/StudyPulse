param(
    [string]$PackageName = "com.studypulse.android",
    [string]$RemoteDir = "",
    [string]$DestinationDir = "",
    [string]$AdbPath = "",
    [string]$DeviceSerial = "",
    [string]$StatusPath = ""
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Write-ProgressLog {
    param([string]$Message)
    Write-Host ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message)
}

function Write-SyncStatus {
    param(
        [string]$Status,
        [string]$Message,
        [string]$LocalPath = "",
        [int64]$Bytes = 0
    )

    if (-not $StatusPath) {
        return
    }

    $statusDir = Split-Path -Parent $StatusPath
    if ($statusDir) {
        New-Item -ItemType Directory -Path $statusDir -Force | Out-Null
    }

    $payload = [ordered]@{
        updated_at = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        status = $Status
        message = $Message
        adb_path = $ResolvedAdb
        device_serial = $DeviceSerial
        remote_dir = $RemoteDir
        destination_dir = $DestinationDir
        local_path = $LocalPath
        bytes = $Bytes
    }
    $payload | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $StatusPath -Encoding UTF8
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

if (-not $RemoteDir) {
    $RemoteDir = "/sdcard/Android/data/$PackageName/files/exports"
}

if (-not $DestinationDir) {
    $DestinationDir = Join-Path ([Environment]::GetFolderPath("Desktop")) ".json"
}

Write-ProgressLog "Progress: start Android ADB JSON sync"
Write-ProgressLog "Progress: remote dir $RemoteDir"
Write-ProgressLog "Progress: destination dir $DestinationDir"
if ($DeviceSerial) {
    Write-ProgressLog "Progress: device serial $DeviceSerial"
}

$ResolvedAdb = Resolve-Adb -ConfiguredPath $AdbPath
if (-not $ResolvedAdb) {
    Write-ProgressLog "Progress: adb.exe not found; skip Android ADB JSON sync"
    Write-SyncStatus -Status "skipped" -Message "adb.exe not found"
    exit 0
}

New-Item -ItemType Directory -Path $DestinationDir -Force | Out-Null
$AdbDeviceArgs = @()
if ($DeviceSerial) {
    $AdbDeviceArgs = @("-s", $DeviceSerial)
}

try {
    $stateOutput = & $ResolvedAdb @AdbDeviceArgs get-state 2>$null
} catch {
    Write-ProgressLog ("Progress: adb.exe could not run; skip Android ADB JSON sync - {0}" -f $_.Exception.Message)
    Write-SyncStatus -Status "failed" -Message ("adb.exe could not run: {0}" -f $_.Exception.Message)
    exit 0
}

if ($LASTEXITCODE -ne 0 -or ($stateOutput -join "").Trim() -ne "device") {
    Write-ProgressLog "Progress: no authorized Android device found; skip Android ADB JSON sync"
    Write-SyncStatus -Status "skipped" -Message "no authorized Android device found"
    exit 0
}

try {
    $remoteList = & $ResolvedAdb @AdbDeviceArgs shell "ls -t $RemoteDir/android_usage*.json 2>/dev/null" 2>$null
} catch {
    Write-ProgressLog ("Progress: adb shell failed; skip Android ADB JSON sync - {0}" -f $_.Exception.Message)
    Write-SyncStatus -Status "failed" -Message ("adb shell failed: {0}" -f $_.Exception.Message)
    exit 0
}

if ($LASTEXITCODE -ne 0 -or -not $remoteList) {
    Write-ProgressLog "Progress: no Android JSON export found on device; skip Android ADB JSON sync"
    Write-SyncStatus -Status "skipped" -Message "no Android JSON export found on device"
    exit 0
}

$latestRemote = ($remoteList | Where-Object { $_ -match "android_usage.*\.json" } | Select-Object -First 1).Trim()
if (-not $latestRemote) {
    Write-ProgressLog "Progress: no valid Android JSON export path returned by adb; skip Android ADB JSON sync"
    Write-SyncStatus -Status "skipped" -Message "no valid Android JSON export path returned by adb"
    exit 0
}

Write-ProgressLog "Progress: pull latest Android JSON $latestRemote"
try {
    & $ResolvedAdb @AdbDeviceArgs pull $latestRemote $DestinationDir | Out-Host
} catch {
    Write-SyncStatus -Status "failed" -Message ("adb pull failed: {0}" -f $_.Exception.Message)
    throw "adb pull failed: $($_.Exception.Message)"
}

if ($LASTEXITCODE -ne 0) {
    Write-SyncStatus -Status "failed" -Message "adb pull failed"
    throw "adb pull failed"
}

$localPath = Join-Path $DestinationDir (Split-Path -Leaf $latestRemote)
if (Test-Path -LiteralPath $localPath) {
    $item = Get-Item -LiteralPath $localPath
    Write-ProgressLog ("Progress: Android JSON synced {0} | {1} bytes" -f $item.FullName, $item.Length)
    Write-SyncStatus -Status "success" -Message "Android JSON synced" -LocalPath $item.FullName -Bytes $item.Length
} else {
    Write-ProgressLog "Progress: adb reported success but local file was not found"
    Write-SyncStatus -Status "failed" -Message "adb reported success but local file was not found"
}
