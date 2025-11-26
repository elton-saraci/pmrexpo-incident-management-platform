import json
import pika
from datetime import datetime

RABBITMQ_HOST = "localhost"
RABBITMQ_QUEUE = "sensor_data"

connection = pika.BlockingConnection(pika.ConnectionParameters(RABBITMQ_HOST))
channel = connection.channel()
channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)

msg = {
    "sensor_id": "sensor-1",
    "incident_id": 1,  # or None
    "metric_type": "temperature",
    "value": 73.4,
    "unit": "C",

    # NEW FIELDS:
    "severity": 7.8,   # 0–10 scale
    "description": "High temperature spike detected near forest boundary",

    # Optional timestamp
    "timestamp": datetime.utcnow().isoformat()
}

channel.basic_publish(
    exchange="",
    routing_key=RABBITMQ_QUEUE,
    body=json.dumps(msg).encode("utf-8"),
    properties=pika.BasicProperties(
        delivery_mode=2  # make message persistent
    )
)

print("Sent test sensor message with severity and description.")
connection.close()
