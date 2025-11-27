import sqlite3
import os

DB_NAME = "crisis_ai.db"
DB_PATH = os.path.join(os.path.dirname(__file__), DB_NAME)


def ensure_incidents_columns(cur: sqlite3.Cursor):
    cur.execute("PRAGMA table_info(incidents);")
    columns = [row[1] for row in cur.fetchall()]

    if "severity_score" not in columns:
        print("Adding column 'severity_score' to incidents table...")
        cur.execute("""
            ALTER TABLE incidents ADD COLUMN severity_score INTEGER DEFAULT 1;
        """)

    if "dispatched_responders" not in columns:
        print("Adding column 'dispatched_responders' to incidents table...")
        cur.execute("""
            ALTER TABLE incidents ADD COLUMN dispatched_responders INTEGER DEFAULT 0;
        """)


def insert_default_fire_departments(cur: sqlite3.Cursor):
    """Insert the 4 Köln fire departments if they do not exist yet."""

    default_departments = [
        {
            "name": "Feuerwache 1 Innenstadt",
            "city": "Köln",
            "latitude": 50.936322,
            "longitude": 6.952140,
            "available_trucks": 4,
            "available_responders": 25
        },
        {
            "name": "Feuerwache 2 Ehrenfeld",
            "city": "Köln",
            "latitude": 50.952280,
            "longitude": 6.917630,
            "available_trucks": 3,
            "available_responders": 8
        },
        {
            "name": "Feuerwache 3 Deutz",
            "city": "Köln",
            "latitude": 50.938180,
            "longitude": 6.974540,
            "available_trucks": 2,
            "available_responders": 20
        },
        {
            "name": "Feuerwache 4 Chorweiler",
            "city": "Köln",
            "latitude": 51.020080,
            "longitude": 6.895820,
            "available_trucks": 2,
            "available_responders": 6
        }
    ]

    for dep in default_departments:
        cur.execute("""
            SELECT id FROM fire_departments WHERE name = ?;
        """, (dep["name"],))
        exists = cur.fetchone()

        if not exists:
            print(f"Inserting default fire department: {dep['name']}")
            cur.execute("""
                INSERT INTO fire_departments
                (name, city, latitude, longitude, available_trucks, available_responders)
                VALUES (?, ?, ?, ?, ?, ?);
            """, (
                dep["name"],
                dep["city"],
                dep["latitude"],
                dep["longitude"],
                dep["available_trucks"],
                dep["available_responders"]
            ))


def create_tables():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("PRAGMA foreign_keys = ON;")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS fire_departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            city TEXT,
            latitude REAL,
            longitude REAL,
            available_trucks INTEGER DEFAULT 0,
            available_responders INTEGER DEFAULT 0
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            description TEXT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            status TEXT DEFAULT 'open',
            severity_score REAL DEFAULT 1,
            priority_score REAL DEFAULT 0.0,
            priority_explanation TEXT,
            dispatched_responders REAL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)

    ensure_incidents_columns(cur)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sensor_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sensor_id TEXT NOT NULL,
            incident_id INTEGER,
            metric_type TEXT,
            value REAL,
            unit TEXT,
            severity REAL,
            description TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(incident_id) REFERENCES incidents(id)
                ON DELETE SET NULL
                ON UPDATE CASCADE
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS recommendation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER NOT NULL,
            recommended_department_id INTEGER,
            priority_score REAL,
            explanation TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(incident_id) REFERENCES incidents(id)
                ON DELETE CASCADE
                ON UPDATE CASCADE,
            FOREIGN KEY(recommended_department_id) REFERENCES fire_departments(id)
                ON DELETE SET NULL
                ON UPDATE CASCADE
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS incident_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            mime_type TEXT,
            storage_path TEXT,
            file_size_bytes INTEGER,
            uploaded_by TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(incident_id) REFERENCES incidents(id)
                ON DELETE CASCADE
                ON UPDATE CASCADE
        );
    """)

    # 🔥 Insert Köln fire departments here
    insert_default_fire_departments(cur)

    conn.commit()
    conn.close()
    print("Database and tables created/updated successfully:", DB_PATH)


if __name__ == "__main__":
    create_tables()
