package com.studypulse.android;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;

import org.json.JSONObject;

import java.io.File;
import java.util.Calendar;

public class DailyExportReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent == null ? "" : intent.getAction();
        if (Intent.ACTION_BOOT_COMPLETED.equals(action)) {
            if (isAutoExportEnabled(context)) {
                scheduleDailyExport(context);
            }
            return;
        }

        if (!UsageExportUtils.ACTION_DAILY_EXPORT.equals(action)) {
            return;
        }

        if (!UsageExportUtils.hasUsageAccess(context)) {
            saveLastExport(context, "failed: Usage Access not granted");
            scheduleDailyExport(context);
            return;
        }

        try {
            JSONObject json = UsageExportUtils.buildTodayUsageJson(context);
            File exported = UsageExportUtils.writeJsonToExternalExports(context, json.toString(2));
            saveLastExport(context, exported.getAbsolutePath());
        } catch (Exception e) {
            saveLastExport(context, "failed: " + e.getMessage());
        } finally {
            scheduleDailyExport(context);
        }
    }

    static void setAutoExportEnabled(Context context, boolean enabled) {
        prefs(context).edit()
                .putBoolean(UsageExportUtils.PREF_AUTO_EXPORT_ENABLED, enabled)
                .apply();
        if (enabled) {
            scheduleDailyExport(context);
        } else {
            cancelDailyExport(context);
        }
    }

    static boolean isAutoExportEnabled(Context context) {
        return prefs(context).getBoolean(UsageExportUtils.PREF_AUTO_EXPORT_ENABLED, false);
    }

    static String getLastExport(Context context) {
        return prefs(context).getString("last_export", "No automatic export yet");
    }

    static void scheduleDailyExport(Context context) {
        AlarmManager alarmManager = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        PendingIntent pendingIntent = buildPendingIntent(context);
        Calendar calendar = Calendar.getInstance();
        calendar.set(Calendar.HOUR_OF_DAY, UsageExportUtils.DAILY_EXPORT_HOUR);
        calendar.set(Calendar.MINUTE, UsageExportUtils.DAILY_EXPORT_MINUTE);
        calendar.set(Calendar.SECOND, 0);
        calendar.set(Calendar.MILLISECOND, 0);
        if (calendar.getTimeInMillis() <= System.currentTimeMillis()) {
            calendar.add(Calendar.DAY_OF_YEAR, 1);
        }
        alarmManager.setInexactRepeating(
                AlarmManager.RTC_WAKEUP,
                calendar.getTimeInMillis(),
                AlarmManager.INTERVAL_DAY,
                pendingIntent
        );
    }

    private static void cancelDailyExport(Context context) {
        AlarmManager alarmManager = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        alarmManager.cancel(buildPendingIntent(context));
    }

    private static PendingIntent buildPendingIntent(Context context) {
        Intent intent = new Intent(context, DailyExportReceiver.class);
        intent.setAction(UsageExportUtils.ACTION_DAILY_EXPORT);
        return PendingIntent.getBroadcast(
                context,
                1001,
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
    }

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(UsageExportUtils.PREFS_NAME, Context.MODE_PRIVATE);
    }

    private static void saveLastExport(Context context, String value) {
        prefs(context).edit().putString("last_export", value).apply();
    }
}
