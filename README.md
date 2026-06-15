# StudyPulse

StudyPulse is a personal learning-behavior dashboard. It combines Android app usage, Windows study-file traces, R activity signals, and an optional MiMo/OpenAI-compatible review into a portable HTML report.

The project is designed for local-first use. It does not read screen content, chat content, notification content, or keystrokes. The Android side exports aggregated usage data; the Windows side scans configured study folders for file activity.

## What It Generates

- Interactive HTML dashboard: `reports/studypulse_ui_interactive.html`
- Static HTML report: `reports/studypulse_sample_report.html`
- Local SQLite database: `data/studypulse.db`
- Pipeline status file: `data/pipeline_status.json`

Generated reports and personal data are intentionally ignored by Git.

## Requirements

- Windows 10/11
- Python 3.10+
- Android phone with StudyPulse Android app installed
- Android Studio / Android SDK for building the Android app
- Optional: ADB for USB or wireless sync
- Optional: Node.js for HTML JavaScript validation
- Optional: MiMo/OpenAI-compatible API key for AI review
- Optional: SMTP account for email delivery

The Python pipeline currently uses only the standard library.

## First-Time Setup

From the project root:

```powershell
cd "C:\path\to\StudyPulse"
python scripts\setup_local_config.py
```

This creates:

```text
config\studypulse.local.json
```

Edit that local file and set:

- `android.export_inbox_dir`: folder where Android JSON exports are collected
- `focus.export_dir`: folder where Tomato ToDo/focus-session JSON files are collected
- `focus.screenshot_inbox_dir`: folder where Tomato ToDo screenshots are collected
- `focus.vision_model`: optional vision-capable OpenAI-compatible model used to turn screenshots into focus JSON
- `study_roots`: folders that contain study files
- `email.recipients`: report recipients
- `features.enable_adb_sync`: whether to try ADB sync
- `features.enable_ai_review`: whether to call MiMo/API
- `features.enable_email`: whether to send email

Do not commit `config\studypulse.local.json`.

## Zero-To-Report Workflow

For a new user, use this order:

1. Generate a local config:

   ```powershell
   python scripts\setup_local_config.py
   ```

2. Edit `config\studypulse.local.json`.

3. Check the environment:

   ```powershell
   python scripts\doctor.py
   ```

4. Verify the UI with sample data:

   ```powershell
   python scripts\run_pipeline.py --sample --skip-email
   ```

5. Install the Android app and grant Usage Access.

6. Export a JSON file from Android, either manually or by ADB sync.

7. Optional: import focus-session data from Tomato ToDo/manual JSON:

   ```powershell
   python scripts\import_focus_export.py sample_data\focus_2026-06-14.json
   ```

8. Run with real data but no email:

   ```powershell
   python scripts\run_pipeline.py --skip-email
   ```

9. Configure SMTP and test email:

   ```powershell
   python scripts\send_report_email.py --dry-run
   ```

10. Run the full pipeline:

   ```powershell
   python scripts\run_pipeline.py
   ```

## Environment Variables

Use `.env.example` as a reference. Required only for optional integrations:

```powershell
setx MIMO_API_KEY "your_api_key"
setx STUDYPULSE_SMTP_HOST "smtp.qq.com"
setx STUDYPULSE_SMTP_PORT "465"
setx STUDYPULSE_SMTP_USER "your_email@example.com"
setx STUDYPULSE_SMTP_PASSWORD "your_app_password"
setx STUDYPULSE_NOTIFY_EMAIL_FROM "your_email@example.com"
```

`STUDYPULSE_NOTIFY_EMAIL_TO` can also be set, but recipients in `config\studypulse.local.json` are supported.

## Check The Environment

Run:

```powershell
python scripts\doctor.py
```

`doctor.py` checks:

- Python version
- selected config file
- Android JSON folder
- latest Android JSON validity
- study folders
- ADB availability
- MiMo API key
- SMTP variables
- email recipients
- Node.js availability
- local SQLite status

Warnings do not always block the product. For example, missing ADB only means automatic phone sync is unavailable.

## Run With Sample Data

Before connecting your own phone data, verify the product page:

```powershell
python scripts\run_pipeline.py --sample --skip-email
```

This uses files under `sample_data` and generates the HTML dashboard without sending email.

## Run With Real Data

Put Android exports in the configured `android.export_inbox_dir`, then run:

```powershell
python scripts\run_pipeline.py --skip-email
```

When the report looks correct and SMTP is configured:

```powershell
python scripts\run_pipeline.py
```

## Focus Session JSON

Android app usage cannot reliably read another app's private study records. StudyPulse treats Tomato ToDo focus sessions as a correction source: after import, the pipeline rewrites Tomato ToDo as a normal `study` app row and folds the corrected minutes into both `phone_total_minutes` and `study_app_minutes`.

If you can only export screenshots, put the Tomato ToDo daily screenshot into:

```text
%USERPROFILE%\Desktop\focus_screenshots
```

Then run:

```powershell
python scripts\import_focus_screenshot.py --latest
```

This requires a vision-capable OpenAI-compatible model. By default the script reuses the `mimo` API settings and `MIMO_API_KEY`; set `focus.vision_model` in `config\studypulse.local.json` if the text model is not image-capable.

The daily pipeline also runs this step automatically in optional mode:

```powershell
python scripts\run_pipeline.py
```

If no screenshot exists or the vision API does not support images, the pipeline continues with existing Android/Windows/R data.

If Tomato ToDo cannot export machine-readable data, create or OCR a daily JSON file with this shape:

```json
{
  "source": "tomato_todo_manual",
  "date": "2026-06-14",
  "sessions": [
    {
      "title": "数学统计做题",
      "start": "12:14",
      "end": "13:07",
      "minutes": 53
    }
  ]
}
```

Import it with:

```powershell
python scripts\import_focus_export.py path\to\focus_2026-06-14.json
```

The file is copied into `focus.export_dir`. The next pipeline run imports it into `focus_sessions`, uses it to correct Tomato ToDo as a normal `study` app, updates `phone_total_minutes` and `study_app_minutes`, and renders the sessions in the product page.

## Android JSON Sync

The Android app saves JSON exports under:

```text
/sdcard/Android/data/com.studypulse.android/files/exports
```

The Windows side can pull those files by ADB if the phone is connected by USB or wireless ADB. If ADB is unavailable, manually copy the JSON file into `android.export_inbox_dir`.

Build the Android app with the included Gradle Wrapper:

```powershell
cd android_app
.\gradlew.bat assembleDebug
```

If the build fails on SDK licenses or Android SDK file permissions, open Android Studio SDK Manager, install Android SDK Platform 35 and Build-Tools, and accept the licenses.

ADB sync writes structured status to:

```text
data\adb_sync_status.json
```

The full pipeline embeds the latest ADB status in:

```text
data\pipeline_status.json
reports\studypulse_ui_interactive.html
```

This means the dashboard should show whether the latest ADB attempt succeeded, was skipped, or failed.

## Daily Automation

Existing Windows helper scripts:

- `scripts\register_android_adb_watch_task.ps1`
- `scripts\register_studypulse_daily_task.ps1`
- `scripts\run_studypulse_daily.ps1`

Recommended flow:

1. Android app exports JSON daily.
2. Windows watcher pulls the latest JSON when ADB is available.
3. Daily pipeline builds the database and reports.
4. Email sends the interactive HTML as an attachment.

## Privacy Notes

Do not commit:

- `.env`
- `config\studypulse.local.json`
- `data\studypulse.db`
- real Android JSON exports
- generated reports
- SMTP passwords or API keys

The repository includes `.gitignore` rules for these files.

See `PRIVACY.md` for the full privacy boundary.

## Troubleshooting

`doctor.py reports ADB missing`

ADB is optional. Manual JSON copy and sample mode still work. For automatic sync, install Android SDK Platform Tools and either add `adb.exe` to `PATH` or set `STUDYPULSE_ADB`.

`adb.exe could not run: Access is denied`

Windows can block `adb.exe` because of permissions, antivirus, or file security flags. Verify the SDK path, run `adb devices` directly, and check whether Windows security is blocking the executable.

`No android_usage*.json found`

Make sure the Android app has exported a JSON file and that `android.export_inbox_dir` points to the same folder where the file was copied or pulled.

`MiMo API call fails`

The report still generates. The AI section will contain a failure message or prompt-only fallback. Check `MIMO_API_KEY`, network access, and the configured `mimo.api_base_url`.

`Email is skipped`

Run:

```powershell
python scripts\send_report_email.py --dry-run
```

Then verify SMTP host, user, app password, sender, and recipients.

## Release Checklist

Before publishing:

```powershell
python scripts\doctor.py
python scripts\validate_project.py
python scripts\run_pipeline.py --sample --skip-email
python scripts\check_release_safety.py
```

Also confirm:

- `config\studypulse.local.json` is not committed.
- `.env` is not committed.
- real Android JSON files are not committed.
- `data\studypulse.db` is not committed.
- generated reports are not committed.
- Android build outputs are not committed.
- the repository license still matches your intended sharing policy.

See `RELEASE_CHECKLIST.md` for the full pre-release list.

## Main Commands

```powershell
python scripts\setup_local_config.py
python scripts\doctor.py
python scripts\run_pipeline.py --sample --skip-email
python scripts\run_pipeline.py --skip-email
python scripts\send_report_email.py --dry-run
python scripts\validate_project.py
python scripts\run_pipeline.py
```
