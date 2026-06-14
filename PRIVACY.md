# StudyPulse Privacy Notes

StudyPulse is designed as a local-first personal analytics tool.

## Data It Uses

StudyPulse can process:

- Android app package names
- Android app foreground usage duration
- Android app open counts estimated from usage events
- Android app last-used timestamps
- local study-file metadata from configured folders
- R command/activity summaries extracted from configured study files
- generated SQLite summaries and HTML reports

## Data It Does Not Read

StudyPulse does not read:

- screen content
- screenshots
- notification content
- chat messages
- keyboard input
- clipboard content
- passwords
- SMS content
- contact lists
- browser page content

## Storage

By default, generated data is stored locally under:

```text
data\
reports\
```

These outputs are ignored by Git and should not be published.

## Email

If email delivery is enabled, StudyPulse sends the generated report to configured recipients through the user's SMTP account. The project does not provide a hosted email service.

## AI Review

If MiMo or another OpenAI-compatible API is enabled, StudyPulse sends aggregated metrics and data-quality summaries to the configured model provider. It should not send raw screen content, chat content, or credentials because those are not collected by the pipeline.

If this is not acceptable for a user's privacy requirements, set:

```json
{
  "features": {
    "enable_ai_review": false
  }
}
```

## Open Source Warning

Before publishing or sharing a repository copy, run:

```powershell
python scripts\check_release_safety.py
```

Also manually confirm that real JSON exports, SQLite databases, generated reports, `.env`, and `config\studypulse.local.json` are not included.
