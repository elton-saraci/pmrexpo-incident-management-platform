import sqlite3

DB_NAME = "crisis_ai.db"

def create_tables():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    # Enable foreign key support (important in SQLite)
    cur.execute("PRAGMA foreign_keys = ON;")

    # --- fire_departments table ---
    cur.execute("""
    CREATE TABLE IF NOT EXISTS fire_departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        city TEXT,
        latitude REAL,
        longitude REAL,
        available_trucks INTEGER DEFAULT 0,
        available_staff INTEGER DEFAULT 0
    );
    """)

    # --- incidents table ---
    cur.execute("""
    CREATE TABLE IF NOT EXISTS incidents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT NOT NULL,              -- forest_fire, blackout, flood, etc.
        description TEXT,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        status TEXT DEFAULT 'open',      -- open, in_progress, resolved
        severity_score REAL DEFAULT 0.0, -- computed by AI
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

       # --- sensor_readings table ---
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sensor_readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sensor_id TEXT NOT NULL,
        incident_id INTEGER,             -- optional (sensor not yet linked to incident)
        metric_type TEXT,                -- temperature, smoke_density, power_load, etc.
        value REAL,
        unit TEXT,
        severity REAL,                   -- NEW: AI/logic severity score for this reading (0–10 or similar)
        description TEXT,                -- NEW: short human-readable description / context
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(incident_id) REFERENCES incidents(id)
            ON DELETE SET NULL
            ON UPDATE CASCADE
    );
    """)

    # --- recommendation_logs table ---
    cur.execute("""
    CREATE TABLE IF NOT EXISTS recommendation_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        incident_id INTEGER NOT NULL,
        recommended_department_id INTEGER,
        priority_score REAL,
        explanation TEXT,                -- why the AI recommended this
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(incident_id) REFERENCES incidents(id)
            ON DELETE CASCADE
            ON UPDATE CASCADE,
        FOREIGN KEY(recommended_department_id) REFERENCES fire_departments(id)
            ON DELETE SET NULL
            ON UPDATE CASCADE
    );
    """)

    # --- incident_attachments table ---
    cur.execute("""
    CREATE TABLE IF NOT EXISTS incident_attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        incident_id INTEGER NOT NULL,
        file_name TEXT NOT NULL,         -- original filename from user
        mime_type TEXT,                  -- image/jpeg, application/pdf, etc.
        storage_path TEXT,               -- where the file is stored (relative/absolute path or URL)
        file_size_bytes INTEGER,         -- optional: size for quick checks
        uploaded_by TEXT,                -- e.g. operator name / user id (optional)
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(incident_id) REFERENCES incidents(id)
            ON DELETE CASCADE
            ON UPDATE CASCADE
    );
    """)

    conn.commit()
    conn.close()
    print("Database and tables created successfully:", DB_NAME)


if __name__ == "__main__":
    create_tables()
