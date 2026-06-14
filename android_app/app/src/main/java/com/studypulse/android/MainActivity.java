package com.studypulse.android;

import android.app.Activity;
import android.content.ClipData;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.provider.Settings;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import androidx.core.content.FileProvider;

import org.json.JSONObject;

import java.io.File;
import java.util.Locale;

public class MainActivity extends Activity {
    private TextView statusView;
    private TextView autoExportView;
    private TextView outputView;
    private String latestJson = "";
    private String latestGeneratedAt = "not refreshed";
    private int latestAppCount = 0;
    private String lastAction = "Open the app, grant Usage Access, then refresh or wait for daily auto export.";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(36, 48, 36, 36);

        statusView = new TextView(this);
        statusView.setTextSize(16);
        root.addView(statusView);

        Button permissionButton = new Button(this);
        permissionButton.setText("Open Usage Access Settings");
        permissionButton.setOnClickListener(v -> startActivity(new Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS)));
        root.addView(permissionButton);

        Button refreshButton = new Button(this);
        refreshButton.setText("Refresh Today Usage");
        refreshButton.setOnClickListener(v -> refreshUsage());
        root.addView(refreshButton);

        Button shareButton = new Button(this);
        shareButton.setText("Share JSON");
        shareButton.setOnClickListener(v -> shareJson());
        root.addView(shareButton);

        Button exportButton = new Button(this);
        exportButton.setText("Save JSON for ADB Sync");
        exportButton.setOnClickListener(v -> saveJsonForAdbSync());
        root.addView(exportButton);

        Button enableAutoExportButton = new Button(this);
        enableAutoExportButton.setText("Enable Daily Auto Export");
        enableAutoExportButton.setOnClickListener(v -> {
            DailyExportReceiver.setAutoExportEnabled(this, true);
            updateAutoExportStatus();
        });
        root.addView(enableAutoExportButton);

        Button disableAutoExportButton = new Button(this);
        disableAutoExportButton.setText("Disable Daily Auto Export");
        disableAutoExportButton.setOnClickListener(v -> {
            DailyExportReceiver.setAutoExportEnabled(this, false);
            updateAutoExportStatus();
        });
        root.addView(disableAutoExportButton);

        autoExportView = new TextView(this);
        autoExportView.setTextSize(13);
        root.addView(autoExportView);

        outputView = new TextView(this);
        outputView.setTextSize(12);

        ScrollView scroll = new ScrollView(this);
        scroll.addView(outputView);
        root.addView(scroll, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                0,
                1
        ));

        setContentView(root);
        refreshUsage();
        updateAutoExportStatus();
    }

    @Override
    protected void onResume() {
        super.onResume();
        updatePermissionStatus();
        updateAutoExportStatus();
    }

    private void updatePermissionStatus() {
        updateStatusPanel();
    }

    private void updateAutoExportStatus() {
        updateStatusPanel();
    }

    private void updateStatusPanel() {
        boolean usageGranted = UsageExportUtils.hasUsageAccess(this);
        boolean enabled = DailyExportReceiver.isAutoExportEnabled(this);
        String exportTime = String.format(Locale.US, "%02d:%02d", UsageExportUtils.DAILY_EXPORT_HOUR, UsageExportUtils.DAILY_EXPORT_MINUTE);
        String lastExport = DailyExportReceiver.getLastExport(this);

        statusView.setText(
                "StudyPulse Sync Status"
                        + "\nUsage Access: " + (usageGranted ? "granted" : "not granted")
                        + "\nToday JSON: " + (latestJson == null || latestJson.isEmpty() ? "not generated in this session" : "ready")
                        + "\nGenerated at: " + latestGeneratedAt
                        + "\nApp rows: " + latestAppCount
                        + "\nNext action: " + lastAction
        );
        autoExportView.setText(
                "Daily Auto Export"
                        + "\nStatus: " + (enabled ? "enabled" : "disabled")
                        + "\nExport time: " + exportTime
                        + "\nLast export: " + lastExport
                        + "\nADB path: " + UsageExportUtils.getAdbExportPath(this)
                        + "\nWindows watcher pulls this folder when the phone is connected by USB or wireless ADB."
        );
    }

    private void refreshUsage() {
        updatePermissionStatus();
        if (!UsageExportUtils.hasUsageAccess(this)) {
            lastAction = "Grant Usage Access, then refresh again.";
            updateStatusPanel();
            outputView.setText("Grant Usage Access first, then refresh.");
            latestJson = "";
            return;
        }

        try {
            JSONObject json = UsageExportUtils.buildTodayUsageJson(this);
            latestJson = json.toString(2);
            latestGeneratedAt = json.optString("generated_at", "unknown");
            latestAppCount = json.optJSONArray("apps") == null ? 0 : json.optJSONArray("apps").length();
            lastAction = "JSON refreshed. Save for ADB sync or wait for daily auto export.";
            updateStatusPanel();
            outputView.setText(latestJson);
        } catch (Exception e) {
            latestJson = "";
            latestGeneratedAt = "refresh failed";
            latestAppCount = 0;
            lastAction = "Refresh failed. Check Usage Access and try again.";
            updateStatusPanel();
            outputView.setText("Failed to read usage stats: " + e.getMessage());
        }
    }

    private void shareJson() {
        if (latestJson == null || latestJson.isEmpty()) {
            refreshUsage();
        }
        if (latestJson == null || latestJson.isEmpty()) {
            return;
        }
        try {
            File jsonFile = UsageExportUtils.writeJsonToCacheExports(this, latestJson);
            lastAction = "Share sheet opened. If sharing fails, use Save JSON for ADB Sync.";
            updateStatusPanel();
            Uri uri = FileProvider.getUriForFile(
                    this,
                    getPackageName() + ".fileprovider",
                    jsonFile
            );

            Intent sendIntent = new Intent(Intent.ACTION_SEND);
            sendIntent.setType("application/json");
            sendIntent.putExtra(Intent.EXTRA_STREAM, uri);
            sendIntent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            sendIntent.setClipData(ClipData.newUri(getContentResolver(), jsonFile.getName(), uri));
            startActivity(Intent.createChooser(sendIntent, "Share StudyPulse JSON file"));
        } catch (Exception e) {
            lastAction = "Share failed. Use Save JSON for ADB Sync instead.";
            updateStatusPanel();
            outputView.setText("Failed to share JSON file: " + e.getMessage() + "\n\n" + latestJson);
        }
    }

    private void saveJsonForAdbSync() {
        if (latestJson == null || latestJson.isEmpty()) {
            refreshUsage();
        }
        if (latestJson == null || latestJson.isEmpty()) {
            return;
        }
        try {
            File jsonFile = UsageExportUtils.writeJsonToExternalExports(this, latestJson);
            lastAction = "Saved for ADB sync. Connect phone to Windows so watcher can pull it.";
            outputView.setText("Saved for ADB sync:\n" + jsonFile.getAbsolutePath() + "\n\n" + latestJson);
            updateAutoExportStatus();
        } catch (Exception e) {
            lastAction = "Save failed. Check storage permission and app data directory.";
            updateStatusPanel();
            outputView.setText("Failed to save JSON for ADB sync: " + e.getMessage() + "\n\n" + latestJson);
        }
    }
}
