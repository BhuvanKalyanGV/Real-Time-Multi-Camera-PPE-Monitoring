# alerts.py
from email_service import send_alert_email
import cv2
from datetime import datetime
import os

os.makedirs("static/snapshots", exist_ok=True)

alerts = []                 # store all alerts
active_alerts = set()       # (camera_id, person_id, violation)


def generate_alert(camera_id, zone, person_id, violation, bbox, frame, frame_id):
    timestamp = datetime.now().strftime("%Y-%m-%d %H-%M-%S")  # safe for filenames

    # Save the full frame instead of cropping
    snapshot_filename = f"frame_{camera_id}_{frame_id}_{timestamp}.jpg"
    snapshot_path = os.path.join("static/snapshots", snapshot_filename)
    cv2.imwrite(snapshot_path, frame)

    alerts.append({
        "camera": camera_id,
        "zone": zone,
        "person_id": person_id,
        "timestamp": timestamp,
        "violation": violation,
        "snapshot": f"snapshots/{snapshot_filename}"  # relative to static/
    })
    send_alert_email(
        camera_id,
        zone,
        person_id,
        violation,
        timestamp,
        snapshot_path
    )