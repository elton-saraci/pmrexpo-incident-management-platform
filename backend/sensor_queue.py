# consumer.py
import json
import os
import sqlite3
from datetime import datetime
import pika

DB_NAME = "crisis_ai.db"

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "sensor_data")


def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    # enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def process_message(body: bytes):
    """
    Parse the incoming JSON and insert into sensor_readings.
    """
    data = json.loads(body.decode("utf-8"))

    sensor_id = data["sensor_id"]
    incident_id = data.get("incident_id") 
    metric_type = data.get("metric_type")
    value = data.get("value")
    unit = data.get("unit")

    # Use current time for now; optionally parse 'timestamp' from data
    timestamp = datetime.utcnow().isoformat()

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO sensor_readings
            (sensor_id, incident_id, metric_type, value, unit, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (sensor_id, incident_id, metric_type, value, unit, timestamp),
    )

    conn.commit()
    conn.close()


def main():
    print(f"[RabbitMQ] Connecting to {RABBITMQ_HOST}, queue '{RABBITMQ_QUEUE}'")

    params = pika.ConnectionParameters(host=RABBITMQ_HOST)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()

    # Make sure the queue exists (idempotent)
    channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)

    def callback(ch, method, properties, body):
        print("[RabbitMQ] Received message:", body)
        try:
            process_message(body)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            print("[RabbitMQ] Error processing message:", e)
            ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=RABBITMQ_QUEUE, on_message_callback=callback)

    print("[RabbitMQ] Waiting for sensor messages. Press CTRL+C to exit.")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        print("\n[RabbitMQ] Stopping consumer...")
        channel.stop_consuming()
    finally:
        connection.close()


if __name__ == "__main__":
    main()
