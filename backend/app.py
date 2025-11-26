from flask import Flask, request, jsonify, send_from_directory, g
from werkzeug.utils import secure_filename
from flask_cors import CORS
import os
import sqlite3
import math
from flasgger import Swagger
import requests 
import json 

AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8081")
DB_NAME = "crisis_ai.db"
UPLOAD_FOLDER = "uploads"
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

def check_for_ai_fakes(file_stream, mime_type):
    """
    Sends an image file stream to the AI service for fake image detection.
    Returns the AI service response body or a default error structure.
    """
    if not mime_type.startswith("image/"):
        # Skip non-image files
        return {"is_fake": False, "confidence": 1.0, "reason": "Not an image, skipped AI check."}

    # Reset file stream position to the beginning before sending
    file_stream.seek(0)
    
    # Prepare the file for multipart/form-data upload to the AI service
    # The 'file_stream' is a SpooledTemporaryFile from Flask's request.files
    files = {
        'file': (file_stream.filename, file_stream, mime_type)
    }

    ai_detection_url = f"{AI_SERVICE_URL}/detect-fake-image"
    
    try:
        # Note: requests.post() handles the multipart/form-data encoding
        response = requests.post(ai_detection_url, files=files, timeout=10)
        
        if response.status_code == 200:
            # AI service returned a successful detection result
            return response.json()
        else:
            # AI service returned an error (e.g., 400 or 500)
            print(f"ERROR: AI Service failed with status {response.status_code}: {response.text}")
            return {
                "is_fake": False, 
                "confidence": 0.0, 
                "reason": f"AI service error: Status {response.status_code} - {response.text[:100]}"
            }

    except requests.exceptions.RequestException as e:
        print(f"ERROR: Failed to connect to AI Service at {ai_detection_url}: {e}")
        return {
            "is_fake": False,
            "confidence": 0.0,
            "reason": f"AI service connection failed: {e}"
        }


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
            ai_reports:
              type: object
              description: Summary of AI detection results for uploaded files
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

            # --- AI DETECTION LOGIC (BEFORE saving) ---
            ai_result = check_for_ai_fakes(f, f.mimetype)
            ai_reports[file_name] = ai_result

            is_fake = ai_result.get("is_fake", False)
            ai_confidence = ai_result.get("confidence", 0.0)
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
                    "ai_reports": ai_reports,
                }), 400

            # --- File Saving (only for NON-fake images) ---
            try:
                f.seek(0)  # reset pointer after AI check
                f.save(fs_path)
            except Exception as e:
                print(f"ERROR: Failed to save file {file_name}: {e}")
                continue  # skip this file, continue with others

            file_size = os.path.getsize(fs_path)
            mime_type = f.mimetype

            # 3) Insert attachment record with AI results
            db.execute(
                """
                INSERT INTO incident_attachments
                    (incident_id, file_name, mime_type, storage_path, file_size_bytes,
                     uploaded_by, ai_is_fake, ai_confidence, ai_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident_id,
                    file_name,
                    mime_type,
                    fs_path,
                    file_size,
                    "public_user",
                    is_fake,
                    ai_confidence,
                    ai_reason,
                ),
            )
            saved_files.append(file_name)

        db.commit()

    return jsonify({
        "incident_id": incident_id,
        "saved_files": saved_files,
        "ai_reports": ai_reports, 
    }), 201


@app.route("/api/incidents/report", methods=["GET"])
def list_incidents():
    """
    List incidents with optional status filter, including attachments (if any)
    ---
    parameters:
      - in: query
        name: status
        type: string
        required: false
        description: Filter by status (open, in_progress, resolved)
    responses:
      200:
        description: A list of incidents (each with attachments array)
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
              attachments:
                type: array
                items:
                  type: object
                  properties:
                    id:
                      type: integer
                    file_name:
                      type: string
                    mime_type:
                      type: string
                    file_size_bytes:
                      type: integer
                    created_at:
                      type: string
                      format: date-time
                    url:
                      type: string
                      description: URL to download / display the file
    """
    status = request.args.get("status")
    db = get_db()

    # 1) Get incidents
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

    # 2) For each incident, fetch attachments and build URLs
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
            # e.g. http://127.0.0.1:5000/uploads/<file_name>
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
            "priority_score": r["priority_score"],
            "priority_explanation": r["priority_explanation"],
            "created_at": r["created_at"],
            "attachments": attachments,  
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
    List fire departments, optionally ranked by distance to an incident
    ---
    parameters:
      - in: query
        name: mode
        type: string
        required: false
        enum: [all, nearest]
        description: >
          all (default) returns all fire departments.
          nearest returns fire departments ranked by distance to a given incident.
      - in: query
        name: incident_id
        type: integer
        required: false
        description: Required when mode=nearest. ID of the incident to measure distance from.
      - in: query
        name: limit
        type: integer
        required: false
        description: Optional limit on number of fire departments to return (used with mode=nearest).
    responses:
      200:
        description: A list of fire departments with mode = all and mode=nearest&incident_id=3&limit=5
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
              distance_km:
                type: number
                description: >
                  Distance from the given incident in kilometers (only present when mode=nearest).
      400:
        description: Invalid parameters (e.g. missing incident_id for mode=nearest)
      404:
        description: Incident not found when mode=nearest
    """
    db = get_db()
    mode = request.args.get("mode", "all")
    incident_id = request.args.get("incident_id", type=int)
    limit = request.args.get("limit", type=int)

    # Fetch all fire departments first
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

    # Mode 1: just return all
    if mode == "all":
        # distance_km not included here
        return jsonify(departments)

    # Mode 2: nearest to an incident
    if mode == "nearest":
        if incident_id is None:
            return jsonify({"error": "incident_id is required when mode=nearest"}), 400

        inc_row = db.execute(
            "SELECT latitude, longitude FROM incidents WHERE id = ?",
            (incident_id,),
        ).fetchone()

        if not inc_row:
            return jsonify({"error": "Incident not found"}), 404

        inc_lat = inc_row["latitude"]
        inc_lon = inc_row["longitude"]

        # Helper: haversine distance
        def haversine_km(lat1, lon1, lat2, lon2):
            # approximate radius of earth in km
            R = 6371.0
            phi1 = math.radians(lat1)
            phi2 = math.radians(lat2)
            dphi = math.radians(lat2 - lat1)
            dlambda = math.radians(lon2 - lon1)

            a = (
                math.sin(dphi / 2) ** 2
                + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
            )
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            return R * c

        # Add distance_km to each department
        for d in departments:
            if d["latitude"] is not None and d["longitude"] is not None:
                d["distance_km"] = round(
                    haversine_km(inc_lat, inc_lon, d["latitude"], d["longitude"]), 2
                )
            else:
                d["distance_km"] = None

        # Sort by distance (None goes last)
        departments.sort(
            key=lambda d: float("inf") if d["distance_km"] is None else d["distance_km"]
        )

        # Apply limit if provided
        if limit is not None and limit > 0:
            departments = departments[:limit]

        return jsonify(departments)

    # Fallback: unknown mode
    return jsonify({"error": "Invalid mode. Use 'all' or 'nearest'."}), 400

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


@app.route("/api/sensors", methods=["GET"])
def list_sensor_readings():
    """
 List sensor readings with optional filters
---
parameters:
  - in: query
    name: incident_id
    type: integer
    required: false
    description: Filter readings only for this incident.
  - in: query
    name: limit
    type: integer
    required: false
    description: Limit number of results (default 50).
responses:
  200:
    description: A list of sensor readings
    schema:
      type: array
      items:
        type: object
        properties:
          id:
            type: integer
          sensor_id:
            type: string
          incident_id:
            type: integer
            nullable: true
          metric_type:
            type: string
          value:
            type: number
          unit:
            type: string
          severity:
            type: number
            description: >
              A severity score for this sensor reading, typically 0–10.
              Can be assigned by the sensor, rule-based logic, or AI.
          description:
            type: string
            description: Short AI/human-readable explanation of the sensor reading.
          timestamp:
            type: string
            format: date-time

    """
    db = get_db()
    incident_id = request.args.get("incident_id", type=int)
    limit = request.args.get("limit", type=int)
    if not limit or limit <= 0:
        limit = 50

    if incident_id is not None:
        rows = db.execute(
            """
            SELECT * FROM sensor_readings
            WHERE incident_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (incident_id, limit),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT * FROM sensor_readings
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    readings = []
    for r in rows:
        readings.append({
            "id": r["id"],
            "sensor_id": r["sensor_id"],
            "incident_id": r["incident_id"],
            "metric_type": r["metric_type"],
            "value": r["value"],
            "unit": r["unit"],
            "severity": r["severity"],          
            "description": r["description"],    
            "timestamp": r["timestamp"],
        })

    return jsonify(readings)

@app.route("/uploads/<path:filename>", methods=["GET"])
def serve_file(filename):
    """
    Serve uploaded files by filename.
    This lets the frontend use the 'url' field in incident attachments.
    """
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)

