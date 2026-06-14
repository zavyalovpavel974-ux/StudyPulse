package com.studypulse.android;

import android.app.AppOpsManager;
import android.app.usage.UsageEvents;
import android.app.usage.UsageStatsManager;
import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Date;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;

final class UsageExportUtils {
    static final String ACTION_DAILY_EXPORT = "com.studypulse.android.ACTION_DAILY_EXPORT";
    static final String PREFS_NAME = "studypulse_export";
    static final String PREF_AUTO_EXPORT_ENABLED = "auto_export_enabled";
    static final int DAILY_EXPORT_HOUR = 23;
    static final int DAILY_EXPORT_MINUTE = 0;

    private UsageExportUtils() {
    }

    static boolean hasUsageAccess(Context context) {
        AppOpsManager appOps = (AppOpsManager) context.getSystemService(Context.APP_OPS_SERVICE);
        int mode = appOps.unsafeCheckOpNoThrow(
                AppOpsManager.OPSTR_GET_USAGE_STATS,
                android.os.Process.myUid(),
                context.getPackageName()
        );
        return mode == AppOpsManager.MODE_ALLOWED;
    }

    static JSONObject buildTodayUsageJson(Context context) throws Exception {
        long end = System.currentTimeMillis();
        Calendar calendar = Calendar.getInstance();
        calendar.set(Calendar.HOUR_OF_DAY, 0);
        calendar.set(Calendar.MINUTE, 0);
        calendar.set(Calendar.SECOND, 0);
        calendar.set(Calendar.MILLISECOND, 0);
        long start = calendar.getTimeInMillis();

        UsageStatsManager manager = (UsageStatsManager) context.getSystemService(Context.USAGE_STATS_SERVICE);
        Map<String, AppUsageAggregate> aggregates = rebuildUsageFromEvents(manager, start, end);

        SimpleDateFormat dateFormat = new SimpleDateFormat("yyyy-MM-dd", Locale.US);
        SimpleDateFormat dateTimeFormat = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US);

        JSONObject root = new JSONObject();
        root.put("schema_version", "1.0");
        root.put("device_type", "android");
        root.put("date", dateFormat.format(new Date(start)));
        root.put("generated_at", dateTimeFormat.format(new Date(end)));

        JSONArray apps = new JSONArray();
        JSONArray hourlyUsage = new JSONArray();
        java.util.List<AppUsageAggregate> sorted = new java.util.ArrayList<>(aggregates.values());
        sorted.sort((left, right) -> Long.compare(right.foregroundMillis, left.foregroundMillis));

        for (AppUsageAggregate item : sorted) {
            if (item.foregroundMillis <= 0) {
                continue;
            }
            JSONObject app = new JSONObject();
            app.put("package_name", item.packageName);
            app.put("app_label", getAppLabel(context, item.packageName));
            app.put("category", "other");
            app.put("foreground_minutes", item.foregroundMillis / 60000.0);
            app.put("open_count", item.openCount);
            app.put("last_used_at", dateTimeFormat.format(new Date(item.lastUsedAt)));
            apps.put(app);

            for (int hour = 0; hour < 24; hour++) {
                if (item.hourlyMillis[hour] <= 0) {
                    continue;
                }
                JSONObject hourItem = new JSONObject();
                hourItem.put("package_name", item.packageName);
                hourItem.put("hour", hour);
                hourItem.put("foreground_minutes", item.hourlyMillis[hour] / 60000.0);
                hourlyUsage.put(hourItem);
            }
        }
        root.put("apps", apps);
        root.put("hourly_usage", hourlyUsage);
        root.put("collection_method", "usage_events_session_rebuild");
        return root;
    }

    static File writeJsonToCacheExports(Context context, String json) throws Exception {
        return writeJsonFile(new File(context.getCacheDir(), "exports"), json);
    }

    static File writeJsonToExternalExports(Context context, String json) throws Exception {
        File exportDir = context.getExternalFilesDir("exports");
        if (exportDir == null) {
            throw new IllegalStateException("External export directory is unavailable");
        }
        return writeJsonFile(exportDir, json);
    }

    static String getAdbExportPath(Context context) {
        return "/sdcard/Android/data/" + context.getPackageName() + "/files/exports";
    }

    private static File writeJsonFile(File exportDir, String json) throws Exception {
        JSONObject parsed = new JSONObject(json);
        String date = parsed.optString("date", new SimpleDateFormat("yyyy-MM-dd", Locale.US).format(new Date()));
        String stamp = new SimpleDateFormat("HHmmss", Locale.US).format(new Date());

        if (!exportDir.exists() && !exportDir.mkdirs()) {
            throw new IllegalStateException("Cannot create export directory");
        }

        File jsonFile = new File(exportDir, "android_usage_" + date + "_" + stamp + ".json");
        try (FileOutputStream output = new FileOutputStream(jsonFile)) {
            output.write(json.getBytes(StandardCharsets.UTF_8));
        }
        return jsonFile;
    }

    private static Map<String, AppUsageAggregate> rebuildUsageFromEvents(UsageStatsManager manager, long start, long end) {
        Map<String, AppUsageAggregate> aggregates = new TreeMap<>();
        Map<String, Long> activeStarts = new HashMap<>();
        UsageEvents events = manager.queryEvents(start, end);
        UsageEvents.Event event = new UsageEvents.Event();
        while (events.hasNextEvent()) {
            events.getNextEvent(event);
            long timestamp = Math.max(start, Math.min(event.getTimeStamp(), end));
            String packageName = event.getPackageName();
            if (packageName == null || packageName.isEmpty()) {
                continue;
            }
            if (event.getEventType() == UsageEvents.Event.ACTIVITY_RESUMED
                    || event.getEventType() == UsageEvents.Event.MOVE_TO_FOREGROUND) {
                AppUsageAggregate aggregate = getAggregate(aggregates, packageName);
                aggregate.openCount += 1;
                aggregate.lastUsedAt = Math.max(aggregate.lastUsedAt, timestamp);
                if (!activeStarts.containsKey(packageName)) {
                    activeStarts.put(packageName, timestamp);
                }
            } else if (event.getEventType() == UsageEvents.Event.ACTIVITY_PAUSED
                    || event.getEventType() == UsageEvents.Event.MOVE_TO_BACKGROUND) {
                Long activeStart = activeStarts.remove(packageName);
                if (activeStart != null && timestamp > activeStart) {
                    addUsage(aggregates, packageName, activeStart, timestamp, start);
                }
            }
        }
        for (Map.Entry<String, Long> entry : activeStarts.entrySet()) {
            if (end > entry.getValue()) {
                addUsage(aggregates, entry.getKey(), entry.getValue(), end, start);
            }
        }
        return aggregates;
    }

    private static AppUsageAggregate getAggregate(Map<String, AppUsageAggregate> aggregates, String packageName) {
        AppUsageAggregate aggregate = aggregates.get(packageName);
        if (aggregate == null) {
            aggregate = new AppUsageAggregate(packageName);
            aggregates.put(packageName, aggregate);
        }
        return aggregate;
    }

    private static void addUsage(Map<String, AppUsageAggregate> aggregates, String packageName, long from, long to, long dayStart) {
        AppUsageAggregate aggregate = getAggregate(aggregates, packageName);
        aggregate.foregroundMillis += Math.max(0, to - from);
        aggregate.lastUsedAt = Math.max(aggregate.lastUsedAt, to);

        long cursor = from;
        while (cursor < to) {
            int hour = (int) ((cursor - dayStart) / (60L * 60L * 1000L));
            if (hour < 0 || hour >= 24) {
                break;
            }
            long nextHour = dayStart + (hour + 1L) * 60L * 60L * 1000L;
            long sliceEnd = Math.min(to, nextHour);
            aggregate.hourlyMillis[hour] += Math.max(0, sliceEnd - cursor);
            cursor = sliceEnd;
        }
    }

    private static String getAppLabel(Context context, String packageName) {
        PackageManager pm = context.getPackageManager();
        try {
            ApplicationInfo info = pm.getApplicationInfo(packageName, 0);
            return pm.getApplicationLabel(info).toString();
        } catch (PackageManager.NameNotFoundException e) {
            return packageName;
        }
    }

    private static final class AppUsageAggregate {
        final String packageName;
        final long[] hourlyMillis = new long[24];
        long foregroundMillis = 0;
        int openCount = 0;
        long lastUsedAt = 0;

        AppUsageAggregate(String packageName) {
            this.packageName = packageName;
        }
    }
}
