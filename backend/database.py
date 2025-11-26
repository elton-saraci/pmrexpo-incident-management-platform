import sqlite3
import os

DB_NAME = "crisis_ai.db"
DB_PATH = os.path.join(os.path.dirname(__file__), DB_NAME)


def ensure_incidents_columns(cur: sqlite3.Cursor):
    """
    Make sure 'severity_score' and 'dispatched_responders' exist
    in the incidents table. If not, add them via ALTER TABLE.
    """
    cur.execute("PRAGMA table_info(incidents);")
    columns = [row[1] for row in cur.fetchall()]  # row[1] = column name

    if "severity_score" not in columns:
        print("Adding column 'severity_score' to incidents table...")
        cur.execute(
            "ALTER TABLE incidents ADD COLUMN severity_score INTEGER DEFAULT 1;"
        )

    if "dispatched_responders" not in columns:
        print("Adding column 'dispatched_responders' to incidents table...")
        cur.execute(
            "ALTER TABLE incidents ADD COLUMN dispatched_responders INTEGER DEFAULT 0;"
        )


def create_tables():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Enable foreign key support (important in SQLite)
    cur.execute("PRAGMA foreign_keys = ON;")

    # --- fire_departments table ---
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS fire_departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        city TEXT,
        latitude REAL,
        longitude REAL,
        available_trucks INTEGER DEFAULT 0,
        available_responders INTEGER DEFAULT 0
    );
    """
    )

    # --- incidents table ---
    # Initial version without the newer columns, then we migrate below.
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS incidents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT NOT NULL,              -- forest_fire, blackout, flood, etc.
        description TEXT,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        status TEXT DEFAULT 'open',      -- open, in_process, resolved
        severity_score REAL DEFAULT 1,
        priority_score REAL DEFAULT 0.0, -- computed by AI
        priority_explanation TEXT,       -- transparent reasoning
        dispatched_responders REAL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """
    )

    # Ensure new columns exist even on old DBs
    ensure_incidents_columns(cur)

    # --- sensor_readings table ---
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS sensor_readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sensor_id TEXT NOT NULL,
        incident_id INTEGER,             -- optional (sensor not yet linked to incident)
        metric_type TEXT,                -- temperature, smoke_density, power_load, etc.
        value REAL,
        unit TEXT,
        severity REAL,                   -- AI/logic severity score for this reading (0–10 or similar)
        description TEXT,                -- short human-readable description / context
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(incident_id) REFERENCES incidents(id)
            ON DELETE SET NULL
            ON UPDATE CASCADE
    );
    """
    )

    # --- recommendation_logs table ---
    cur.execute(
        """
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
    """
    )

    # --- incident_attachments table ---
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS incident_attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        incident_id INTEGER NOT NULL,
        file_name TEXT NOT NULL,         -- original filename from user
        mime_type TEXT,                  -- image/jpeg, application/pdf, etc.
        storage_path TEXT,               -- where the file is stored (relative/absolute path or URL)
        file_size_bytes INTEGER,         -- size for quick checks
        uploaded_by TEXT,                -- e.g. operator name / user id (optional)
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(incident_id) REFERENCES incidents(id)
            ON DELETE CASCADE
            ON UPDATE CASCADE
    );
    """
    )

    conn.commit()
    conn.close()
    print("Database and tables created/updated successfully:", DB_PATH)


if __name__ == "__main__":
    create_tables()
