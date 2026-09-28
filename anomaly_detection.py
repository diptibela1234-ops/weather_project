"""
anomaly_detection.py
---------------------
Simple RULE-BASED anomaly detection. No machine learning needed.

For every new reading, each parameter (temperature, humidity, pressure,
wind_speed) is checked against these rules:

1. SPIKE   -> value suddenly jumps a lot compared to the last reading
2. FROZEN  -> value hasn't changed at all for several readings in a row
              (usually means the sensor is stuck)
3. DRIFT   -> value is slowly and steadily climbing or falling over time
              (usually means the sensor needs recalibration)
4. MISSING -> the sensor didn't send a value for this parameter at all,
              OR the sensor hasn't sent ANY reading for a while (see
              check_sensor_silence)

Tweak the numbers in PARAMETER_RULES below to make detection more or
less sensitive - that's the easiest way to "tune" this system.
"""

import database
from datetime import datetime, timezone

# How much change counts as a problem, per parameter.
PARAMETER_RULES = {
    "temperature": {"unit": "°C",   "spike_change": 8,  "drift_change": 5,  "frozen_readings": 5},
    "humidity":    {"unit": "%",    "spike_change": 25, "drift_change": 15, "frozen_readings": 5},
    "pressure":    {"unit": "hPa",  "spike_change": 12, "drift_change": 8,  "frozen_readings": 5},
    "wind_speed":  {"unit": "km/h", "spike_change": 20, "drift_change": 10, "frozen_readings": 5},
}

# How many points to deduct from the health score for each anomaly type found
PENALTIES = {
    "spike": 8,
    "drift": 5,
    "frozen": 15,
    "missing_data": 10,
}

# If a sensor hasn't sent a single reading in this many minutes, treat it as silent/offline
SILENCE_THRESHOLD_MINUTES = 30


def detect_anomalies(new_values, history):
    """
    Compare one new reading against recent history and return a list of anomalies found.

    new_values: dict like {"temperature": 25.4, "humidity": 60, "pressure": 1012, "wind_speed": 10}
                (any of these can be None if the sensor didn't send that value)
    history:    list of past reading dicts for the SAME sensor, oldest first.

    Returns a list of dicts: {"parameter", "anomaly_type", "value", "message"}
    """
    anomalies = []

    for param, rules in PARAMETER_RULES.items():
        value = new_values.get(param)

        # ---- Rule: MISSING DATA ----
        if value is None:
            anomalies.append({
                "parameter": param,
                "anomaly_type": "missing_data",
                "value": None,
                "message": f"No '{param}' value was included in this reading."
            })
            continue

        # Only look at past readings where this parameter was actually recorded
        past_values = [h[param] for h in history if h.get(param) is not None]

        # ---- Rule: SPIKE (big sudden jump from the last known value) ----
        if past_values:
            last_value = past_values[-1]
            change = abs(value - last_value)
            if change >= rules["spike_change"]:
                anomalies.append({
                    "parameter": param,
                    "anomaly_type": "spike",
                    "value": value,
                    "message": (f"{param} jumped from {last_value} to {value} {rules['unit']} "
                                f"(change of {change:.1f})")
                })

        # ---- Rule: FROZEN / STUCK (identical value repeated) ----
        needed = rules["frozen_readings"] - 1
        last_n = past_values[-needed:] if needed > 0 else []
        if len(last_n) == needed and all(abs(v - value) < 0.01 for v in last_n):
            anomalies.append({
                "parameter": param,
                "anomaly_type": "frozen",
                "value": value,
                "message": (f"{param} has stayed at {value} {rules['unit']} for "
                            f"{rules['frozen_readings']} readings in a row - sensor may be stuck")
            })

        # ---- Rule: DRIFT (slow steady change over recent readings) ----
        window = past_values[-6:]
        if len(window) == 6:
            older_avg = sum(window[:3]) / 3
            newer_avg = sum(window[3:]) / 3
            drift = newer_avg - older_avg
            if abs(drift) >= rules["drift_change"]:
                direction = "increasing" if drift > 0 else "decreasing"
                anomalies.append({
                    "parameter": param,
                    "anomaly_type": "drift",
                    "value": value,
                    "message": (f"{param} has been steadily {direction} "
                                f"(drift of {abs(drift):.1f} {rules['unit']} over recent readings)")
                })

    return anomalies


def calculate_health_score(sensor_id):
    """
    Very simple scoring: start at 100 points, subtract a penalty for each
    recent anomaly. Looks at the sensor's most recent 20 anomaly log entries.
    """
    recent = database.get_recent_anomalies(sensor_id, limit=20)

    counts = {}
    for anomaly in recent:
        counts[anomaly["anomaly_type"]] = counts.get(anomaly["anomaly_type"], 0) + 1

    score = 100
    for anomaly_type, count in counts.items():
        score -= PENALTIES.get(anomaly_type, 5) * count

    score = max(0, min(100, score))

    if score >= 80:
        status = "Healthy"
    elif score >= 50:
        status = "Warning"
    else:
        status = "Critical"

    return score, status


def check_sensor_silence(last_reading_timestamp):
    """
    Returns (is_silent, minutes_since_last_reading).
    is_silent is True if the sensor hasn't reported in over SILENCE_THRESHOLD_MINUTES.
    """
    if isinstance(last_reading_timestamp, datetime):
        last_time = last_reading_timestamp
    else:
        last_time = datetime.fromisoformat(last_reading_timestamp)

    if last_time.tzinfo is None:
        last_time = last_time.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    
    gap_minutes = (now - last_time).total_seconds() / 60

    return gap_minutes > SILENCE_THRESHOLD_MINUTES, gap_minutes