import mysql.connector


def get_connection():
    connection = mysql.connector.connect(
        host="localhost",
        user="root",
        password="Coder@2320",
        database="aws_monitoring"
    )
    return connection

def get_recent_readings(station_id, limit=10):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        query = """
            SELECT *
            FROM sensor_readings
            WHERE station_id = %s
            ORDER BY recorded_at DESC
            LIMIT %s
        """

        cursor.execute(query, (station_id, limit))
        readings = cursor.fetchall()

        return readings

    finally:
        cursor.close()
        connection.close()


def insert_reading(station_id, timestamp, temperature, humidity, pressure, wind_speed):
    connection = get_connection()
    cursor = connection.cursor()
    try:
        query = """
            INSERT INTO sensor_readings (station_id, recorded_at, temperature, humidity, pressure, wind_speed)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query, (station_id, timestamp, temperature, humidity, pressure, wind_speed))
        connection.commit()
    finally:
        cursor.close()
        connection.close()


def get_latest_reading(station_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        query = """
            SELECT *
            FROM sensor_readings
            WHERE station_id = %s
            ORDER BY recorded_at DESC
            LIMIT 1
        """
        cursor.execute(query, (station_id,))
        return cursor.fetchone()
    finally:
        cursor.close()
        connection.close()


def get_all_sensor_ids():
    connection = get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT DISTINCT station_id FROM sensor_readings")
        rows = cursor.fetchall()
        return [row[0] for row in rows]
    finally:
        cursor.close()
        connection.close()


def insert_anomaly(station_id, timestamp, parameter, anomaly_type, value, message):
    connection = get_connection()
    cursor = connection.cursor()
    try:
        query = """
            INSERT INTO anomalies (station_id, detected_at, parameter, anomaly_type, observed_value , description)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query, (station_id, timestamp, parameter, anomaly_type, value, message))
        connection.commit()
    finally:
        cursor.close()
        connection.close()


def get_recent_anomalies(station_id, limit=10):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        query = """
            SELECT *
            FROM anomalies
            WHERE station_id = %s
            ORDER BY detected_at DESC
            LIMIT %s
        """
        cursor.execute(query, (station_id, limit))
        return cursor.fetchall()
    finally:
        cursor.close()
        connection.close()


def get_anomalies(sensor_id=None, limit=50):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        if sensor_id:
            query = """
                SELECT *
                FROM anomalies
                WHERE station_id = %s
                ORDER BY detected_at DESC
                LIMIT %s
            """
            cursor.execute(query, (sensor_id, limit))
        else:
            query = """
                SELECT *
                FROM anomalies
                ORDER BY detected_at DESC
                LIMIT %s
            """
            cursor.execute(query, (limit,))
        return cursor.fetchall()
    finally:
        cursor.close()
        connection.close()


def update_health_score(station_id, score, status):
    connection = get_connection()
    cursor = connection.cursor()
    try:
        query = """
            INSERT INTO sensor_health (station_id, health_score, status, last_updated)
            VALUES (%s, %s, %s, NOW())
            ON DUPLICATE KEY UPDATE
                health_score = VALUES(health_score),
                status = VALUES(status),
                last_updated = NOW()
        """
        cursor.execute(query, (station_id, score, status))
        connection.commit()
    finally:
        cursor.close()
        connection.close()


def get_health(station_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        query = """
            SELECT *
            FROM sensor_health
            WHERE station_id = %s
        """
        cursor.execute(query, (station_id,))
        return cursor.fetchone()
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    try:
        connection = get_connection()

        if connection.is_connected():
            print("Database connected to backend successfully!")

        connection.close()

    except Exception as e:
        print("Database connection failed:", e)
#database.init_db()