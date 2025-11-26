from flask import Flask, request, jsonify, send_from_directory, g
from werkzeug.utils import secure_filename
from flask_cors import CORS
import os
import sqlite3
import math
from flasgger import Swagger
import requests

from database import create_tables, DB_PATH  # make sure database.py defines these

AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8081")
DB_NAME = DB_PATH  # use the same path as in database.py
UPLOAD_FOLDER = "uploads"

# Ensure DB and tables exist on startup
create_tables()

app = Flask(__name__)
CORS(app, supports_credentials=True)
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


# --- AI IMAGE FAKE DETECTION ---

def check_for_ai_fakes(file_stream, mime_type):
    """
    Sends an image file stream to the AI service for fake image detection.
    Returns the AI service response body or a default error structure.
    """
    if not mime_type.startswith("image/"):
        # Skip non-image files
        return {
            "is_fake": False,
            "confidence": 1.0,
            "reason": "Not an image, skipped AI check.",
        }

    file_stream.seek(0)

    files = {
        "file": (file_stream.filename, file_stream, mime_type)
    }

    ai_detection_url = f"{AI_SERVICE_URL}/detect-fake-image"

    try:
        response = requests.post(ai_detection_url, files=files, timeout=10)

        if response.status_code == 200:
            return response.json()
        else:
            print(
                f"ERROR: AI Service failed with status {response.status_code}: "
                f"{response.text}"
            )
            return {
                "is_fake": False,
                "confidence": 0.0,
                "reason": (
                    f"AI service error: Status {response.status_code} - "
                    f"{response.text[:100]}"
                ),
            }

    except requests.exceptions.RequestException as e:
        print(f"ERROR: Failed to connect to AI Service at {ai_detection_url}: {e}")
        return {
            "is_fake": False,
            "confidence": 0.0,
            "reason": f"AI service connection failed: {e}",
        }


# --- AI RESOURCE ALLOCATION CALL ---

def call_ai_resource_allocation(
    incident_id: int,
    inc_type: str,
    lat: float,
    lon: float,
    severity_score: int,
    db: sqlite3.Connection,
):
    """
    Build the resource-allocation payload and call the AI service.

    Returns a dict:
      {
        "success": bool,
        "status_code": int|None,
        "data": <json>|None,
        "error": str|None
      }
    """
    fd_rows = db.execute(
        """
        SELECT id, name, latitude, longitude, available_staff
        FROM fire_departments
        """
    ).fetchall()

    fire_departments_nearby = []
    for row in fd_rows:
        if row["latitude"] is None or row["longitude"] is None:
            continue

        fire_departments_nearby.append({
            "id": str(row["id"]),
            "name": row["name"],
            "location": {
                "latitude": row["latitude"],
                "longitude": row["longitude"],
            },
            "available_responders": row["available_staff"] or 0,
        })

    payload = {
        "incidents": [
            {
                "id": str(incident_id),
                "type": inc_type,
                "incident_geo_data": {
                    "latitude": lat,
                    "longitude": lon,
                },
                "severity_score": severity_score,
                "fire_departments_nearby": fire_departments_nearby,
            }
        ]
    }

    ai_url = f"{AI_SERVICE_URL}/resource-allocation"

    try:
        resp = requests.post(ai_url, json=payload, timeout=10)
        if resp.status_code in (200, 201):
            return {
                "success": True,
                "status_code": resp.status_code,
                "data": resp.json(),
                "error": None,
            }
        else:
            print(
                f"WARNING: AI resource allocation failed "
                f"status={resp.status_code}, body={resp.text[:200]}"
            )
            return {
                "success": False,
                "status_code": resp.status_code,
                "data": None,
                "error": resp.text[:200],
            }
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Could not reach AI resource allocation service at {ai_url}: {e}")
        return {
            "success": False,
            "status_code": None,
            "data": None,
            "error": str(e),
        }


# --- INCIDENT CRUD ENDPOINTS ---

@app.route("/api/incidents/report", methods=["POST"])
def report_incident_with_files():
    """
    Report a new incident with optional file attachments

    Allows severity_score in the payload (defaults to 1 if missing/empty).
    Also calls the AI resource allocation service and updates the incident
    with dispatched responders and status.

    ---
    tags:
      - incidents
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
        name: severity_score
        type: integer
        required: false
        description: Severity of the incident (1..5). Defaults to 1 if empty.
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
            severity_score:
              type: integer
      400:
        description: Missing or invalid parameters
    """
    db = get_db()
    cur = db.cursor()

    inc_type = request.form.get("type")
    lat = request.form.get("latitude")
    lon = request.form.get("longitude")
    desc = request.form.get("description")
    severity_raw = request.form.get("severity_score")

    if not inc_type or lat is None or lon is None:
        return jsonify({"error": "type, latitude, longitude are required as form fields"}), 400

    try:
        lat = float(lat)
        lon = float(lon)
    except ValueError:
        return jsonify({"error": "latitude and longitude must be numeric"}), 400

    # severity_score: if null/empty/invalid -> default to 1
    if severity_raw is None or str(severity_raw).strip() == "":
        severity_score = 1
    else:
        try:
            severity_score = int(severity_raw)
        except ValueError:
            severity_score = 1

    # 1) Create incident including severity_score
    cur.execute(
        """
        INSERT INTO incidents (type, description, latitude, longitude, severity_score)
        VALUES (?, ?, ?, ?, ?)
        """,
        (inc_type, desc, lat, lon, severity_score),
    )
    db.commit()
    incident_id = cur.lastrowid

    # 2) Handle files + AI fake detection
    saved_files = []
    ai_reports = {}

    if "files" in request.files:
        files = request.files.getlist("files")

        for f in files:
            if f.filename == "":
                continue

            original_name = f.filename
            safe_name = secure_filename(original_name)
            file_name = f"{incident_id}_{safe_name}"
            fs_path = os.path.join(app.config["UPLOAD_FOLDER"], file_name)

            ai_result = check_for_ai_fakes(f, f.mimetype)
            ai_reports[file_name] = ai_result

            is_fake = ai_result.get("is_fake", False)
            ai_reason = ai_result.get("reason", "")

            if is_fake:
                db.execute("DELETE FROM incidents WHERE id = ?", (incident_id,))
                db.commit()

                return jsonify({
                    "error": "fake_image_detected",
                    "message": (
                        f"File '{original_name}' was flagged as fake by the AI detector. "
                        f"Reason: {ai_reason}"
                    ),
                    "incident_id": incident_id,
                }), 400

            try:
                f.seek(0)
                f.save(fs_path)
            except Exception as e:
                print(f"ERROR: Failed to save file {file_name}: {e}")
                continue

            file_size = os.path.getsize(fs_path)
            mime_type = f.mimetype

            db.execute(
                """
                INSERT INTO incident_attachments
                    (incident_id, file_name, mime_type, storage_path, file_size_bytes,
                     uploaded_by)
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

    # 3) Call AI resource allocation
    ai_resource_result = call_ai_resource_allocation(
        incident_id=incident_id,
        inc_type=inc_type,
        lat=lat,
        lon=lon,
        severity_score=severity_score,
        db=db,
    )

    # 4) Update DB with assignments
    dispatched_total = 0

    if ai_resource_result.get("success") and ai_resource_result.get("data"):
        data = ai_resource_result["data"]
        incidents_data = data.get("incidents", [])
        for inc in incidents_data:
            if str(incident_id) != str(inc.get("id")):
                continue
            assignments = inc.get("assignments", [])
            for assignment in assignments:
                fd_id_str = assignment.get("fire_department_id")
                dispatched = assignment.get("responders_dispatched", 0) or 0

                try:
                    fd_id = int(fd_id_str)
                except (TypeError, ValueError):
                    continue

                db.execute(
                    """
                    UPDATE fire_departments
                    SET available_staff = CASE
                        WHEN available_staff >= ?
                        THEN available_staff - ?
                        ELSE 0
                    END
                    WHERE id = ?
                    """,
                    (dispatched, dispatched, fd_id),
                )
                dispatched_total += dispatched

        if dispatched_total > 0:
            db.execute(
                """
                UPDATE incidents
                SET status = 'in_process',
                    dispatched_responders = ?
                WHERE id = ?
                """,
                (dispatched_total, incident_id),
            )
            db.commit()

    response_body = {
        "incident_id": incident_id,
        "saved_files": saved_files,
        "severity_score": severity_score,
    }

    if ai_resource_result.get("success"):
        response_body["resource_allocation"] = ai_resource_result.get("data")
    else:
        response_body["resource_allocation_error"] = ai_resource_result.get("error")

    return jsonify(response_body), 201


@app.route("/api/incidents/report", methods=["GET"])
def list_incidents():
    """
    List incidents with optional status filter, including attachments (if any)
    ---
    tags:
      - incidents
    parameters:
      - in: query
        name: status
        type: string
        required: false
        description: Filter by status (open, in_process, resolved)
    responses:
      200:
        description: A list of incidents
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
        incident_id = r["id"]

        att_rows = db.execute(
            """
            SELECT id, file_name, mime_type, file_size_bytes, created_at
            FROM incident_attachments
            WHERE incident_id = ?
            ORDER BY created_at DESC
            """,
            (incident_id,),
        ).fetchall()

        attachments = []
        for a in att_rows:
            file_name = a["file_name"]
            file_url = request.host_url.rstrip("/") + "/uploads/" + file_name

            attachments.append({
                "id": a["id"],
                "file_name": file_name,
                "mime_type": a["mime_type"],
                "file_size_bytes": a["file_size_bytes"],
                "created_at": a["created_at"],
                "url": file_url,
            })

        incidents.append({
            "id": r["id"],
            "type": r["type"],
            "description": r["description"],
            "latitude": r["latitude"],
            "longitude": r["longitude"],
            "status": r["status"],
            "severity_score": r["severity_score"],
            "priority_score": r["priority_score"],
            "priority_explanation": r["priority_explanation"],
            "dispatched_responders": r["dispatched_responders"],
            "created_at": r["created_at"],
            "attachments": attachments,
        })

    return jsonify(incidents)


# --- FIRE DEPARTMENT ENDPOINTS ---

@app.route("/api/fire_departments", methods=["GET"])
def get_all_fire_departments():
    """
    List all fire departments
    ---
    tags:
      - fire_departments
    responses:
      200:
        description: A list of all fire departments in the database
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
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
    """
    db = get_db()
    rows = db.execute("SELECT * FROM fire_departments").fetchall()

    departments = [
        {
            "id": r["id"],
            "name": r["name"],
            "city": r["city"],
            "latitude": r["latitude"],
            "longitude": r["longitude"],
            "available_trucks": r["available_trucks"],
            "available_staff": r["available_staff"],
        }
        for r in rows
    ]

    return jsonify(departments)


@app.route("/api/fire_departments", methods=["POST"])
def create_or_update_fire_department():
    """
    Create or update a fire department.

    If the payload does not contain an "id", a new fire department is created.
    If the payload contains an "id", the existing department with that id is updated.
    ---
    tags:
      - fire_departments
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            id:
              type: integer
              description: Existing fire-department id (for update). Omit for create.
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
      200:
        description: Fire department updated
      400:
        description: Invalid input data
      404:
        description: Fire department not found (for update)
    """
    db = get_db()
    cur = db.cursor()

    data = request.get_json(force=True) or {}

    fd_id = data.get("id")
    name = data.get("name")
    city = data.get("city")
    lat = data.get("latitude")
    lon = data.get("longitude")
    trucks = data.get("available_trucks", 0)
    staff = data.get("available_staff", 0)

    if not name:
        return jsonify({"error": "name is required"}), 400

    # CREATE
    if fd_id is None:
        cur.execute(
            """
            INSERT INTO fire_departments
                (name, city, latitude, longitude, available_trucks, available_staff)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, city, lat, lon, trucks, staff),
        )
        db.commit()
        new_id = cur.lastrowid

        row = db.execute(
            "SELECT * FROM fire_departments WHERE id = ?",
            (new_id,),
        ).fetchone()

        return (
            jsonify(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "city": row["city"],
                    "latitude": row["latitude"],
                    "longitude": row["longitude"],
                    "available_trucks": row["available_trucks"],
                    "available_staff": row["available_staff"],
                }
            ),
            201,
        )

    # UPDATE
    row = cur.execute(
        "SELECT * FROM fire_departments WHERE id = ?",
        (fd_id,),
    ).fetchone()

    if not row:
        return jsonify({"error": "Fire department not found"}), 404

    cur.execute(
        """
        UPDATE fire_departments
        SET name = ?, city = ?, latitude = ?, longitude = ?,
            available_trucks = ?, available_staff = ?
        WHERE id = ?
        """,
        (name, city, lat, lon, trucks, staff, fd_id),
    )
    db.commit()

    row = db.execute(
        "SELECT * FROM fire_departments WHERE id = ?",
        (fd_id,),
    ).fetchone()

    return jsonify(
        {
            "id": row["id"],
            "name": row["name"],
            "city": row["city"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "available_trucks": row["available_trucks"],
            "available_staff": row["available_staff"],
        }
    )


# --- SENSOR READINGS ---

def list_sensor_readings():
    """
    Report a new incident based on a sensor reading (JSON-only payload).
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
            type:
              type: string
              description: Type of incident (forest_fire, blackout, flood, etc.)
            latitude:
              type: number
              description: Latitude of the incident
            longitude:
              type: number
              description: Longitude of the incident
            description:
              type: string
              description: Free-text description of the incident
            severity_score:
              type: number
              description: Severity of the incident
    responses:
      201:
        description: Incident created successfully
        schema:
          type: object
          properties:
            incident_id:
              type: integer
      400:
        description: Missing or invalid parameters
    """
    
    db = get_db()
    cur = db.cursor()

    inc_type = request.form.get("type")
    lat = request.form.get("latitude")
    lon = request.form.get("longitude")
    desc = request.form.get("description")
    severity_score = request.form.get("severity_score")

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
        INSERT INTO incidents (type, description, latitude, longitude, severity_score)
        VALUES (?, ?, ?, ?, ?)
        """,
        (inc_type, desc, lat, lon, severity_score),
    )
    db.commit()
    incident_id = cur.lastrowid

    return jsonify({
        "incident_id": incident_id,
    }), 201


# --- FILE SERVING FOR UPLOADS ---

@app.route("/uploads/<path:filename>", methods=["GET"])
def serve_file(filename):
    """
    Serve uploaded files by filename.
    """
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

@app.route("/api/incidents/<int:incident_id>/status", methods=["PUT"])
def update_incident_status(incident_id: int):
    """
    Update the status of an incident.

    When the status is updated and the incident had dispatched responders,
    those responders are returned to a fire department (we add them back to
    the nearest fire department by distance) and the incident's
    dispatched_responders is reset to 0.

    ---
    tags:
      - incidents
    consumes:
      - application/json
    parameters:
      - in: path
        name: incident_id
        type: integer
        required: true
        description: ID of the incident to update
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            status:
              type: string
              enum: [open, in_process, resolved]
              description: New status for the incident
    responses:
      200:
        description: Incident updated successfully
      400:
        description: Invalid status or payload
      404:
        description: Incident not found
    """
    db = get_db()
    cur = db.cursor()

    # 1) Parse and validate payload
    data = request.get_json(force=True) or {}
    new_status = data.get("status")

    allowed_statuses = {"open", "in_process", "resolved"}
    if new_status not in allowed_statuses:
        return jsonify({
            "error": "Invalid status",
            "allowed": list(allowed_statuses)
        }), 400

    # 2) Fetch incident
    row = cur.execute(
        "SELECT * FROM incidents WHERE id = ?",
        (incident_id,)
    ).fetchone()

    if not row:
        return jsonify({"error": "Incident not found"}), 404

    old_status = row["status"]
    dispatched = row["dispatched_responders"] or 0
    inc_lat = row["latitude"]
    inc_lon = row["longitude"]

    # 3) If responders were dispatched and we are "closing" the incident
    #    (e.g., moving away from in_process), then return responders to a FD.
    #    For simplicity, we return them to the nearest fire department.
    if old_status == "in_process" and dispatched > 0 and new_status != "in_process":
        fd_rows = db.execute("SELECT * FROM fire_departments").fetchall()

        nearest_fd = None
        nearest_dist = None

        for fd in fd_rows:
            fd_lat = fd["latitude"]
            fd_lon = fd["longitude"]
            if fd_lat is None or fd_lon is None:
                continue

            # Haversine distance
            R = 6371.0
            lat1 = math.radians(inc_lat)
            lon1 = math.radians(inc_lon)
            lat2 = math.radians(fd_lat)
            lon2 = math.radians(fd_lon)
            dlat = lat2 - lat1
            dlon = lon2 - lon1

            a = (
                math.sin(dlat / 2) ** 2
                + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
            )
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            dist_km = R * c

            if nearest_dist is None or dist_km < nearest_dist:
                nearest_dist = dist_km
                nearest_fd = fd

        if nearest_fd is not None:
            fd_id = nearest_fd["id"]
            # Return responders to this fire department
            db.execute(
                """
                UPDATE fire_departments
                SET available_staff = available_staff + ?
                WHERE id = ?
                """,
                (dispatched, fd_id),
            )
            # Reset dispatched_responders to 0 for this incident
            db.execute(
                """
                UPDATE incidents
                SET dispatched_responders = 0
                WHERE id = ?
                """,
                (incident_id,),
            )

    # 4) Update incident status
    db.execute(
        """
        UPDATE incidents
        SET status = ?
        WHERE id = ?
        """,
        (new_status, incident_id),
    )
    db.commit()

    # 5) Return updated incident
    updated = db.execute(
        "SELECT * FROM incidents WHERE id = ?",
        (incident_id,),
    ).fetchone()

    return jsonify({
        "id": updated["id"],
        "type": updated["type"],
        "description": updated["description"],
        "latitude": updated["latitude"],
        "longitude": updated["longitude"],
        "status": updated["status"],
        "severity_score": updated["severity_score"],
        "priority_score": updated["priority_score"],
        "priority_explanation": updated["priority_explanation"],
        "dispatched_responders": updated["dispatched_responders"],
        "created_at": updated["created_at"],
    })


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
