# StudyPulse Release Checklist

Use this checklist before publishing the repository.

## Required Checks

```powershell
python scripts\doctor.py
python scripts\validate_project.py
python scripts\run_pipeline.py --sample --skip-email
python scripts\check_release_safety.py
```

## Files That Must Not Be Published

- `.env`
- `config\studypulse.local.json`
- `config\studypulse_config.json`
- `data\studypulse.db`
- `data\pipeline_status.json`
- `data\adb_sync_status.json`
- real `android_usage*.json`
- generated `reports\*.html`
- Android build outputs under `android_app\app\build`
- `android_app\local.properties`

## Documentation Checks

- README includes first-time setup.
- README explains sample mode.
- README explains real-data mode.
- README explains SMTP dry-run.
- Android README explains Usage Access.
- Android README explains manual JSON export.
- Android README explains ADB sync.
- Android README explains common ADB failures.

## Product Checks

- `doctor.py` has no failures.
- Sample pipeline generates an HTML report.
- Real-data pipeline can run with `--skip-email`.
- HTML JavaScript parses successfully.
- Dashboard shows the latest ADB sync status.
- Dashboard shows data credibility, formulas, and pipeline state.

## Open Source License

The repository currently includes an MIT license. Confirm that this matches your intended sharing policy before publishing.
