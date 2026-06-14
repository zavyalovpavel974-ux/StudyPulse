# StudyPulse Android App

This directory contains the Android collector app for StudyPulse. The app exports aggregated Android app-usage metadata into JSON files that the Windows pipeline can import.

## Privacy Boundary

The Android app does not collect:

- screen content
- notification content
- chat content
- typed input
- account credentials
- SMS content
- contact lists

It only reads Android `UsageStats` / usage events after the user grants Usage Access permission.

## Main Features

- Open Android Usage Access settings.
- Read current-day foreground app usage.
- Rebuild approximate foreground sessions from UsageEvents.
- Export a StudyPulse-compatible JSON file.
- Save JSON to the app external files directory for ADB sync.
- Enable daily automatic export at about 23:00.

## Build With Android Studio

Recommended path:

1. Install Android Studio.
2. Open this directory:

   ```text
   android_app
   ```

3. Wait for Gradle Sync.
4. Select an Android device.
5. Run the `app` configuration.

The project includes a Gradle Wrapper. New contributors do not need to install Gradle globally.

## Build From Command Line

```powershell
cd "C:\path\to\StudyPulse\android_app"
.\gradlew.bat assembleDebug
```

The debug APK is usually generated under:

```text
android_app\app\build\outputs\apk\debug\
```

On macOS or Linux:

```bash
cd /path/to/StudyPulse/android_app
./gradlew assembleDebug
```

## First Run On Phone

1. Install and open StudyPulse.
2. Tap `OPEN USAGE ACCESS SETTINGS`.
3. Enable Usage Access for StudyPulse in Android settings.
4. Return to StudyPulse.
5. Tap `REFRESH TODAY USAGE`.

The status panel should show whether Usage Access is granted and whether a JSON export is available.

## Manual Export

Tap:

```text
SHARE JSON
```

This writes a real `.json` file first, then shares the file through Android `FileProvider`.

Do not manually copy the long JSON text from the screen. Large text can be truncated by the clipboard or target app, which causes invalid JSON on Windows.

## Save For ADB Sync

Tap:

```text
SAVE JSON FOR ADB SYNC
```

The file is saved under:

```text
/sdcard/Android/data/com.studypulse.android/files/exports
```

The Windows pipeline pulls the newest matching file:

```text
android_usage*.json
```

into the configured Windows inbox folder, usually:

```text
%USERPROFILE%\Desktop\.json
```

## Daily Auto Export

Tap:

```text
ENABLE DAILY AUTO EXPORT
```

The app schedules a daily export at about 23:00.

Important Android behavior:

- Battery optimization may delay background work.
- Some systems restrict background execution aggressively.
- Reboot is supported by the app receiver, but the app should be opened once after installation.
- If the app is force-stopped manually, Android may prevent scheduled work until the app is opened again.

## USB ADB Sync

Phone requirements:

- Developer options enabled.
- USB debugging enabled.
- The current computer authorized on the phone.

Windows test command:

```powershell
adb devices
```

Expected state:

```text
device
```

Then from the project root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\sync_android_json_adb.ps1
```

The sync script writes a structured status file:

```text
data\adb_sync_status.json
```

The daily pipeline embeds this status into:

```text
data\pipeline_status.json
reports\studypulse_ui_interactive.html
```

## Wireless ADB

Wireless ADB is supported as long as the Windows command below lists the phone as `device`:

```powershell
adb devices
```

Wireless devices usually appear as:

```text
phone-ip:port    device
```

After wireless ADB is connected, the same Windows sync script works.

## Common Problems

`adb.exe not found`

Set `STUDYPULSE_ADB` to the full path of `adb.exe`, or add Android SDK `platform-tools` to `PATH`.

`adb.exe could not run: Access is denied`

Check whether antivirus, permissions, or another process is blocking `adb.exe`. Try running PowerShell normally, then as administrator if needed. Also verify that the file is not blocked by Windows security settings.

`no authorized Android device found`

Run `adb devices`, unlock the phone, and accept the debugging authorization prompt.

`no Android JSON export found on device`

Open StudyPulse on the phone and tap `SAVE JSON FOR ADB SYNC`, then run the Windows sync again.

`SDK license has not been accepted`

Open Android Studio, install the required SDK Platform and Build Tools through SDK Manager, and accept the licenses. You can also run:

```powershell
sdkmanager --licenses
```

`AccessDeniedException` for Android SDK files

Check permissions for the Android SDK directory. On Windows this is usually:

```text
%LOCALAPPDATA%\Android\Sdk
```

If `package.xml` under `platforms\android-35` is inaccessible, repair or reinstall that SDK platform from Android Studio SDK Manager.

## Current Limitations

- UsageStats is system-provided metadata, not precise screen recording.
- App categories may initially be `other`; the Windows pipeline refines categories with `config/app_category_rules.csv`.
