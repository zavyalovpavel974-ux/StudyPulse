PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS import_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    file_name TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    message TEXT
);

CREATE TABLE IF NOT EXISTS app_category_rule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    package_name TEXT,
    app_label TEXT,
    category TEXT NOT NULL CHECK (category IN ('study', 'tool', 'social', 'entertainment', 'game', 'other')),
    note TEXT
);

CREATE TABLE IF NOT EXISTS android_app_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    package_name TEXT NOT NULL,
    app_label TEXT,
    category TEXT NOT NULL CHECK (category IN ('study', 'tool', 'social', 'entertainment', 'game', 'other')),
    foreground_minutes REAL NOT NULL DEFAULT 0,
    open_count INTEGER NOT NULL DEFAULT 0,
    last_used_at TEXT,
    import_id INTEGER,
    FOREIGN KEY (import_id) REFERENCES import_log(id)
);

CREATE INDEX IF NOT EXISTS idx_android_app_usage_date
ON android_app_usage(date);

CREATE TABLE IF NOT EXISTS android_app_hourly_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    package_name TEXT NOT NULL,
    app_label TEXT,
    category TEXT NOT NULL CHECK (category IN ('study', 'tool', 'social', 'entertainment', 'game', 'other')),
    hour INTEGER NOT NULL CHECK (hour BETWEEN 0 AND 23),
    foreground_minutes REAL NOT NULL DEFAULT 0,
    import_id INTEGER,
    FOREIGN KEY (import_id) REFERENCES import_log(id)
);

CREATE INDEX IF NOT EXISTS idx_android_app_hourly_usage_date_package
ON android_app_hourly_usage(date, package_name);

CREATE TABLE IF NOT EXISTS app_name_mapping (
    package_name TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'rule',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS data_quality_report (
    date TEXT PRIMARY KEY,
    android_source_file TEXT,
    android_generated_at TEXT,
    collection_method TEXT,
    raw_app_rows INTEGER NOT NULL DEFAULT 0,
    aggregated_app_rows INTEGER NOT NULL DEFAULT 0,
    duplicate_package_count INTEGER NOT NULL DEFAULT 0,
    unknown_app_count INTEGER NOT NULL DEFAULT 0,
    system_app_count INTEGER NOT NULL DEFAULT 0,
    suspicious_app_count INTEGER NOT NULL DEFAULT 0,
    notes_json TEXT NOT NULL DEFAULT '[]',
    generated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS windows_file_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    root_alias TEXT NOT NULL,
    relative_path TEXT,
    path_hash TEXT NOT NULL,
    extension TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL DEFAULT 0,
    last_modified_at TEXT NOT NULL,
    activity_type TEXT NOT NULL CHECK (activity_type IN ('created', 'modified', 'unknown')),
    import_id INTEGER,
    FOREIGN KEY (import_id) REFERENCES import_log(id)
);

CREATE INDEX IF NOT EXISTS idx_windows_file_activity_date
ON windows_file_activity(date);

CREATE TABLE IF NOT EXISTS r_history_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    history_file_hash TEXT NOT NULL,
    command_count INTEGER NOT NULL DEFAULT 0,
    package_count INTEGER NOT NULL DEFAULT 0,
    data_import_count INTEGER NOT NULL DEFAULT 0,
    data_cleaning_count INTEGER NOT NULL DEFAULT 0,
    visualization_count INTEGER NOT NULL DEFAULT 0,
    statistics_count INTEGER NOT NULL DEFAULT 0,
    modeling_count INTEGER NOT NULL DEFAULT 0,
    other_count INTEGER NOT NULL DEFAULT 0,
    top_packages_json TEXT NOT NULL DEFAULT '[]',
    top_functions_json TEXT NOT NULL DEFAULT '[]',
    import_id INTEGER,
    FOREIGN KEY (import_id) REFERENCES import_log(id)
);

CREATE INDEX IF NOT EXISTS idx_r_history_summary_date
ON r_history_summary(date);

CREATE TABLE IF NOT EXISTS daily_metrics (
    date TEXT PRIMARY KEY,
    phone_total_minutes REAL NOT NULL DEFAULT 0,
    study_app_minutes REAL NOT NULL DEFAULT 0,
    tool_app_minutes REAL NOT NULL DEFAULT 0,
    social_app_minutes REAL NOT NULL DEFAULT 0,
    entertainment_app_minutes REAL NOT NULL DEFAULT 0,
    game_app_minutes REAL NOT NULL DEFAULT 0,
    distracting_app_minutes REAL NOT NULL DEFAULT 0,
    distracting_ratio REAL NOT NULL DEFAULT 0,
    app_open_count INTEGER NOT NULL DEFAULT 0,
    total_study_files_count INTEGER NOT NULL DEFAULT 0,
    study_files_modified_7d_count INTEGER NOT NULL DEFAULT 0,
    study_files_modified_count INTEGER NOT NULL DEFAULT 0,
    study_files_created_count INTEGER NOT NULL DEFAULT 0,
    r_command_count INTEGER NOT NULL DEFAULT 0,
    r_visualization_count INTEGER NOT NULL DEFAULT 0,
    r_modeling_count INTEGER NOT NULL DEFAULT 0,
    learning_input_score REAL NOT NULL DEFAULT 0,
    learning_output_score REAL NOT NULL DEFAULT 0,
    distraction_risk_score REAL NOT NULL DEFAULT 0,
    r_activity_score REAL NOT NULL DEFAULT 0,
    generated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weekly_metrics (
    week_start TEXT NOT NULL,
    week_end TEXT NOT NULL,
    avg_learning_input_score REAL NOT NULL DEFAULT 0,
    avg_learning_output_score REAL NOT NULL DEFAULT 0,
    avg_distraction_risk_score REAL NOT NULL DEFAULT 0,
    total_study_app_minutes REAL NOT NULL DEFAULT 0,
    total_distracting_app_minutes REAL NOT NULL DEFAULT 0,
    total_study_files_modified INTEGER NOT NULL DEFAULT 0,
    total_r_commands INTEGER NOT NULL DEFAULT 0,
    data_days_count INTEGER NOT NULL DEFAULT 0,
    is_partial_week INTEGER NOT NULL DEFAULT 1,
    best_day TEXT,
    risk_day TEXT,
    generated_at TEXT NOT NULL,
    PRIMARY KEY (week_start, week_end)
);

CREATE TABLE IF NOT EXISTS monthly_metrics (
    month_start TEXT PRIMARY KEY,
    month_end TEXT NOT NULL,
    avg_learning_input_score REAL NOT NULL DEFAULT 0,
    avg_learning_output_score REAL NOT NULL DEFAULT 0,
    avg_distraction_risk_score REAL NOT NULL DEFAULT 0,
    total_study_app_minutes REAL NOT NULL DEFAULT 0,
    total_distracting_app_minutes REAL NOT NULL DEFAULT 0,
    total_study_files_modified INTEGER NOT NULL DEFAULT 0,
    total_r_commands INTEGER NOT NULL DEFAULT 0,
    data_days_count INTEGER NOT NULL DEFAULT 0,
    is_partial_month INTEGER NOT NULL DEFAULT 1,
    best_day TEXT,
    risk_day TEXT,
    generated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_review (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL CHECK (scope IN ('daily', 'weekly')),
    target_date TEXT,
    week_start TEXT,
    week_end TEXT,
    prompt TEXT NOT NULL,
    review_text TEXT,
    model_name TEXT,
    generated_at TEXT NOT NULL
);
