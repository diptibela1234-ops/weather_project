"""
app.py
------
Main Flask application. Run this file to start the backend server:

    python app.py

It will start on http://127.0.0.1:5000
"""

from datetime import datetime, timezone

from flask import Flask, render_template, request, jsonify
render_template
from flask_cors import CORS

import database
import anomaly_detection
from weather_ml_model import get_weather_and_detect

app = Flask(__name__)
CORS(app)  # allow the frontend (running on any origin/port) to call this API

# Make sure the database file and tables exist before we handle any requests
#database.init_db()

METRIC_FIELDS = ["temperature", "humidity", "pressure", "wind_speed"]


# ---------------------------------------------------------------------------
# CORE LOGIC (shared by the API route and mock_data.py)
# ---------------------------------------------------------------------------

def process_reading(station_id, values, timestamp=None):
    """
    The full pipeline for one incoming reading:
      1. save it
      2. run rule-based anomaly detection on it
      3. save any anomalies found
      4. recalculate the sensor's health score
    Returns a summary dict that the API sends back to the frontend.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()

    # Get history BEFORE inserting the new reading, so we have something to compare against
    history = database.get_recent_readings(station_id, limit=10)

    database.insert_reading(
        station_id,
        timestamp,
        values.get("temperature"),
        values.get("humidity"),
        values.get("pressure"),
        values.get("wind_speed"),
    )

    found_anomalies = anomaly_detection.detect_anomalies(values, history)

    for anomaly in found_anomalies:
        database.insert_anomaly(
            station_id,
            timestamp,
            anomaly["parameter"],
            anomaly["anomaly_type"],
            anomaly["value"],
            anomaly["message"],
        )

    score, status = anomaly_detection.calculate_health_score(station_id)
    database.update_health_score(station_id, score, status)

    return {
        "sensor_id": station_id,
        "timestamp": timestamp,
        "reading": values,
        "anomalies_detected": found_anomalies,
        "health_score": score,
        "status": status,
    }


def get_sensor_status(sensor_id):
    """Latest reading + a freshly recalculated health score/status for one sensor."""
    latest = database.get_latest_reading(sensor_id)
    if not latest:
        return None

    is_silent, gap_minutes = anomaly_detection.check_sensor_silence(latest["recorded_at"])

    if is_silent:
        # Only log a fresh "missing_data" anomaly if we haven't already logged one for this gap
        recent = database.get_recent_anomalies(sensor_id, limit=3)
        already_flagged = any(
            a["anomaly_type"] == "missing_data" and a["parameter"] == "all" for a in recent
        )
        if not already_flagged:
            database.insert_anomaly(
                sensor_id, datetime.now(timezone.utc).isoformat(), "all",
                "missing_data", None,
                f"Sensor has not sent any data for {int(gap_minutes)} minutes."
            )

    score, status = anomaly_detection.calculate_health_score(sensor_id)
    if is_silent:
        status = "Offline"

    database.update_health_score(sensor_id, score, status)

    return {
        "sensor_id": sensor_id,
        "latest_reading": latest,
        "health_score": score,
        "status": status,
        "minutes_since_last_reading": round(gap_minutes, 1),
    }


# ---------------------------------------------------------------------------
# ROUTES
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def home():
    return render_template(
        "index.html",
        
    )


@app.route("/api/data", methods=["POST"])
def add_sensor_readings():
    data = request.get_json(silent=True)

    if data is None:
        return jsonify({"error": "Request body must be valid JSON."}), 400

    sensor_id = data.get("sensor_id")
    if not sensor_id or not isinstance(sensor_id, str):
        return jsonify({"error": "'sensor_id' (text) is required."}), 400

    values = {}
    for field in METRIC_FIELDS:
        if field in data and data[field] is not None:
            try:
                values[field] = float(data[field])
            except (TypeError, ValueError):
                return jsonify({"error": f"'{field}' must be a number."}), 400
        else:
            values[field] = None  # missing -> will be flagged as a missing_data anomaly

    if all(v is None for v in values.values()):
        return jsonify({
            "error": "At least one reading value (temperature, humidity, pressure, or wind_speed) is required."
        }), 400

    timestamp = data.get("timestamp")  # optional - if not given, current time is used
    if timestamp:
        try:
            datetime.fromisoformat(timestamp)
        except ValueError:
            return jsonify({
                "error": "'timestamp' must be a valid ISO 8601 string, e.g. 2026-09-12T10:00:00"
            }), 400

    result = process_reading(sensor_id, values, timestamp)
    return jsonify(result), 201


@app.route("/api/sensors", methods=["GET"])
def list_sensors():
    sensor_ids = database.get_all_sensor_ids()
    sensors = [get_sensor_status(sid) for sid in sensor_ids]
    sensors = [s for s in sensors if s is not None]
    return jsonify({"count": len(sensors), "sensors": sensors})


@app.route("/api/sensors/<sensor_id>/current", methods=["GET"])
def sensor_current(sensor_id):
    latest = database.get_latest_reading(sensor_id)
    if not latest:
        return jsonify({"error": f"No data found for sensor '{sensor_id}'."}), 404
    return jsonify(latest)


@app.route("/api/sensors/<sensor_id>/history", methods=["GET"])
def sensor_history(sensor_id):
    limit = request.args.get("limit", default=50, type=int) or 50
    limit = max(1, min(limit, 500))  # keep requests reasonable

    readings = database.get_recent_readings(sensor_id, limit=limit)
    if not readings:
        return jsonify({"error": f"No data found for sensor '{sensor_id}'."}), 404

    return jsonify({"sensor_id": sensor_id, "count": len(readings), "readings": readings})


@app.route("/api/sensors/<sensor_id>/health", methods=["GET"])
def sensor_health(sensor_id):
    status_info = get_sensor_status(sensor_id)
    if not status_info:
        return jsonify({"error": f"No data found for sensor '{sensor_id}'."}), 404

    health = database.get_health(sensor_id)

    return jsonify({
        "sensor_id": sensor_id,
        "health_score": status_info["health_score"],
        "status": status_info["status"],
        "minutes_since_last_reading": status_info["minutes_since_last_reading"],
        "last_updated": health["last_updated"] if health else None,
    })


@app.route("/api/anomalies", methods=["GET"])
def list_anomalies():
    sensor_id = request.args.get("sensor_id")  # optional filter
    limit = request.args.get("limit", default=50, type=int) or 50
    limit = max(1, min(limit, 500))

    anomalies = database.get_anomalies(sensor_id=sensor_id, limit=limit)
    return jsonify({"count": len(anomalies), "anomalies": anomalies})


# ---------------------------------------------------------------------------
# ERROR HANDLERS (so the frontend always gets clean JSON, never an HTML error page)
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found."}), 404


@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "Method not allowed on this endpoint."}), 405


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error."}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

