from flask import Flask, request, jsonify, send_from_directory, g
from werkzeug.utils import secure_filename
import os
import sqlite3
from flasgger import Swagger

DB_NAME = "crisis_ai.db"
UPLOAD_FOLDER = "uploads"
app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

swagger = Swagger(app)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# --- DB CONNECTION HELPERS ---

def get_db():
    if "db" not in g:
        
        g.db = sqlite3.connect(DB_NAME, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON;")
        g.db.execute("PRAGMA journal_mode = WAL;")
        g.db.execute("PRAGMA busy_timeout = 10000;")
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# --- INCIDENT CRUD ENDPOINTS ---

@app.route("/api/incidents/report", methods=["POST"])
def report_incident_with_files():
        
    """
    Report a new incident with optional file attachments
    ---
    consumes:
      - multipart/form-data
    parameters:
      - in: formData
        name: type
        type: string
        required: true
        description: Type of incident (forest_fire, blackout, flood, etc.)
      - in: formData
        name: latitude
        type: number
        required: true
        description: Latitude of the incident
      - in: formData
        name: longitude
        type: number
        required: true
        description: Longitude of the incident
      - in: formData
        name: description
        type: string
        required: false
        description: Free-text description of the incident
      - in: formData
        name: files
        type: file
        required: false
        description: One or more files (images, PDFs, etc.)
        multiple: true
    responses:
      201:
        description: Incident created successfully
        schema:
          type: object
          properties:
            incident_id:
              type: integer
            saved_files:
              type: array
              items:
                type: string
      400:
        description: Missing or invalid parameters
    """
    db = get_db()
    cur = db.cursor()

    inc_type = request.form.get("type")
    lat = request.form.get("latitude")
    lon = request.form.get("longitude")
    desc = request.form.get("description")

    if not inc_type or lat is None or lon is None:
        return jsonify({"error": "type, latitude, longitude are required as form fields"}), 400

    try:
        lat = float(lat)
        lon = float(lon)
    except ValueError:
        return jsonify({"error": "latitude and longitude must be numeric"}), 400

    # 1) Create incident
    cur.execute(
        """
        INSERT INTO incidents (type, description, latitude, longitude)
        VALUES (?, ?, ?, ?)
        """,
        (inc_type, desc, lat, lon),
    )
    db.commit()
    incident_id = cur.lastrowid

    # 2) Handle files (if any)
    saved_files = []

    if "files" in request.files:
        files = request.files.getlist("files")

        for f in files:
            if f.filename == "":
                continue

            # secure filename and make it unique by prefixing incident id
            original_name = f.filename
            safe_name = secure_filename(original_name)
            file_name = f"{incident_id}_{safe_name}"
            fs_path = os.path.join(app.config["UPLOAD_FOLDER"], file_name)
            f.save(fs_path)

            file_size = os.path.getsize(fs_path)
            mime_type = f.mimetype

            db.execute(
                """
                INSERT INTO incident_attachments
                    (incident_id, file_name, mime_type, storage_path, file_size_bytes, uploaded_by)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    incident_id,
                    file_name,
                    mime_type,
                    fs_path,
                    file_size,
                    "public_user",
                ),
            )
            saved_files.append(file_name)

        db.commit()

    return jsonify({
        "incident_id": incident_id,
        "saved_files": saved_files,
    }), 201


@app.route("/api/incidents/report", methods=["GET"])
def list_incidents():
    """
    List incidents with optional status filter
    ---
    parameters:
      - in: query
        name: status
        type: string
        required: false
        description: Filter by status (open, in_progress, resolved)
    responses:
      200:
        description: A list of incidents
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
              type:
                type: string
              description:
                type: string
              latitude:
                type: number
              longitude:
                type: number
              status:
                type: string
              priority_score:
                type: number
              priority_explanation:
                type: string
              created_at:
                type: string
                format: date-time
    """
    status = request.args.get("status")
    db = get_db()
    if status:
        rows = db.execute(
            "SELECT * FROM incidents WHERE status = ? ORDER BY created_at DESC",
            (status,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM incidents ORDER BY created_at DESC"
        ).fetchall()

    incidents = []
    for r in rows:
        incidents.append({
            "id": r["id"],
            "type": r["type"],
            "description": r["description"],
            "latitude": r["latitude"],
            "longitude": r["longitude"],
            "status": r["status"],
            "priority_score": r["priority_score"],
            "priority_explanation": r["priority_explanation"],
            "created_at": r["created_at"],
        })
    return jsonify(incidents)

# --- FIRE DEPARTMENTS CRUD ENDPOINTS ---

@app.route("/api/fire_departments", methods=["POST"])
def create_fire_department():
    """
    Create a new fire department
    ---
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
            city:
              type: string
            latitude:
              type: number
            longitude:
              type: number
            available_trucks:
              type: integer
            available_staff:
              type: integer
    responses:
      201:
        description: Fire department created
        schema:
          type: object
          properties:
            id:
              type: integer
      400:
        description: Invalid input data
    """
    data = request.get_json(force=True)
    name = data.get("name")
    city = data.get("city")
    lat = data.get("latitude")
    lon = data.get("longitude")
    trucks = data.get("available_trucks", 0)
    staff = data.get("available_staff", 0)

    if not name:
        return jsonify({"error": "name is required"}), 400

    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO fire_departments
            (name, city, latitude, longitude, available_trucks, available_staff)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (name, city, lat, lon, trucks, staff),
    )
    db.commit()

    return jsonify({"id": cur.lastrowid}), 201


@app.route("/api/fire_departments", methods=["GET"])
def list_fire_departments():
    """
    List all fire departments.
    """
    db = get_db()
    rows = db.execute("SELECT * FROM fire_departments").fetchall()

    fds = []
    for r in rows:
        fds.append({
            "id": r["id"],
            "name": r["name"],
            "city": r["city"],
            "latitude": r["latitude"],
            "longitude": r["longitude"],
            "available_trucks": r["available_trucks"],
            "available_staff": r["available_staff"],
        })
    return jsonify(fds)


@app.route("/api/fire_departments/<int:fd_id>", methods=["GET"])
def get_fire_department(fd_id):
    """
    Get a single fire department by id.
    """
    db = get_db()
    row = db.execute(
        "SELECT * FROM fire_departments WHERE id = ?",
        (fd_id,),
    ).fetchone()

    if not row:
        return jsonify({"error": "Fire department not found"}), 404

    return jsonify({
        "id": row["id"],
        "name": row["name"],
        "city": row["city"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "available_trucks": row["available_trucks"],
        "available_staff": row["available_staff"],
    })


@app.route("/api/fire_departments/<int:fd_id>", methods=["PATCH"])
def update_fire_department(fd_id):
    """
    Partially update a fire department.

    Any of these fields are allowed:
    name, city, latitude, longitude, available_trucks, available_staff
    """
    data = request.get_json(force=True)
    db = get_db()

    row = db.execute(
        "SELECT * FROM fire_departments WHERE id = ?",
        (fd_id,),
    ).fetchone()
    if not row:
        return jsonify({"error": "Fire department not found"}), 404

    fields = []
    values = []

    for field in ["name", "city", "latitude", "longitude", "available_trucks", "available_staff"]:
        if field in data:
            fields.append(f"{field} = ?")
            values.append(data[field])

    if fields:
        values.append(fd_id)
        db.execute(
            f"UPDATE fire_departments SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        db.commit()

    row = db.execute(
        "SELECT * FROM fire_departments WHERE id = ?",
        (fd_id,),
    ).fetchone()
    return jsonify({
        "id": row["id"],
        "name": row["name"],
        "city": row["city"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "available_trucks": row["available_trucks"],
        "available_staff": row["available_staff"],
    })


@app.route("/api/fire_departments/<int:fd_id>", methods=["DELETE"])
def delete_fire_department(fd_id):
    """
    Delete a fire department.
    """
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM fire_departments WHERE id = ?", (fd_id,))
    db.commit()

    if cur.rowcount == 0:
        return jsonify({"error": "Fire department not found"}), 404

    return jsonify({"deleted": True})

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)

