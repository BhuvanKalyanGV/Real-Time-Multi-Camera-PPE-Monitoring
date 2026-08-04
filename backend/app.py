import time

VIOLATION_THRESHOLD = 2.0   # seconds required to trigger alert
ALERT_COOLDOWN = 5.0        # seconds before same alert allowed again

violation_tracker = {}

ZONE_RULES = {
    "Excavation": {"Helmet", "Vest"},
    "Welding": {"Helmet", "Vest"},          
    "Height": {"Helmet"},
    "Cement": {"Helmet"},
    "None": set()
}

CAMERA_ZONES = {
    1: "Excavation",
    2: "Excavation",
    3: "Excavation",
    4: "Excavation"
}

from flask import request, redirect, url_for
from flask import Flask, Response, render_template
import cv2
from ultralytics import YOLO
from alerts import generate_alert, alerts
from cjm_byte_track.core import BYTETracker
import numpy as np


app = Flask(__name__)

# Load model ONCE
model = YOLO("../models/best.pt")
model.model.fuse = lambda *args, **kwargs: model.model

# Camera sources (can be video files / webcams / RTSP)
CAMERA_SOURCES = {
    1: "../sample_videos/TestVideo1.mp4",
    2: "../sample_videos/TestVideo2.mp4",
    3: "../sample_videos/TestVideo3.mp4",
    4: "../sample_videos/TestVideo4.mp4",
}
trackers = {
    cam_id: BYTETracker(
        track_thresh=0.3,
        track_buffer=30,
        match_thresh=0.8,
        frame_rate=30
    )
    for cam_id in CAMERA_SOURCES
}

caps = {i: cv2.VideoCapture(src) for i, src in CAMERA_SOURCES.items()}

CLASS_NAMES = ['Helmet', 'No-Helmet', 'No-Vest', 'Person', 'Vest']

FRAME_SKIP = 6  # run YOLO every 6th frame


from cjm_byte_track.core import BYTETracker
import numpy as np

# Tracker setup (outside generate_frames)
tracker = BYTETracker(track_thresh=0.3, track_buffer=30, match_thresh=0.8, frame_rate=30)

def generate_frames(cam_id):

    cap = caps[cam_id]
    tracker = trackers[cam_id]

    frame_id = 0
    last_results = []

    while True:
        frame_id += 1
        success, frame = cap.read()
        if not success:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue

        frame = cv2.resize(frame, (640, 360))

        # ---------- YOLO ----------
        if frame_id % FRAME_SKIP == 0:
            last_results = model(frame, conf=0.25, iou=0.5)
        results = last_results

        person_boxes = []
        helmet_boxes = []
        vest_boxes = []

        # ---------- PARSE DETECTIONS ----------
        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                label = CLASS_NAMES[cls_id]
                x1, y1, x2, y2 = map(int, box.xyxy[0])

                if label == "Person":
                    person_boxes.append([x1, y1, x2, y2, conf])

                elif label in ["Helmet", "No-Helmet"]:
                    helmet_boxes.append([x1, y1, x2, y2, label])

                elif label in ["Vest", "No-Vest"]:
                    vest_boxes.append([x1, y1, x2, y2, label])

        # ---------- TRACK PERSON ----------
        if person_boxes:
            dets = np.array(person_boxes)
            tracks = tracker.update(dets, frame.shape[:2], frame.shape[:2])
        else:
            tracks = []

        # ---------- ZONE LOGIC ----------
        zone = CAMERA_ZONES.get(cam_id, "None")
        required_ppe = ZONE_RULES.get(zone, set())

        check_helmet = "Helmet" in required_ppe
        check_vest = "Vest" in required_ppe

        # ---------- PER PERSON ----------
        for track in tracks:
            px1, py1, px2, py2 = map(int, track.tlbr)
            person_id = track.track_id

            has_helmet = False
            has_vest = True if not check_vest else False  # 🔥 FIX
            helmet_box = None
            vest_box = None

            # ---- HELMET MATCH ----
            if check_helmet:
                for hx1, hy1, hx2, hy2, label in helmet_boxes:
                    if not (hx2 < px1 or hx1 > px2 or hy2 < py1 or hy1 > py2):
                        helmet_box = (hx1, hy1, hx2, hy2)
                        if label == "Helmet":
                            has_helmet = True

            # ---- VEST MATCH (ONLY IF REQUIRED) ----
            if check_vest:
                for vx1, vy1, vx2, vy2, label in vest_boxes:
                    if not (vx2 < px1 or vx1 > px2 or vy2 < py1 or vy1 > py2):
                        vest_box = (vx1, vy1, vx2, vy2)
                        if label == "Vest":
                            has_vest = True

            # ---------- COMPLIANCE ----------
            compliant = (
                (not check_helmet or has_helmet) and
                (not check_vest or has_vest)
            )

            person_color = (0, 255, 0) if compliant else (0, 0, 255)

            cv2.rectangle(frame, (px1, py1), (px2, py2), person_color, 2)
            cv2.putText(
                frame,
                f"ID:{person_id} | {zone}",
                (px1, py1 - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                person_color,
                2
            )

            # ---------- DRAW HELMET ----------
            if helmet_box:
                hx1, hy1, hx2, hy2 = helmet_box
                color = (0, 255, 0) if has_helmet else (0, 0, 255)
                cv2.rectangle(frame, (hx1, hy1), (hx2, hy2), color, 2)

            # ---------- DRAW VEST (ONLY IF REQUIRED) ----------
            if check_vest and vest_box:
                vx1, vy1, vx2, vy2 = vest_box
                color = (0, 255, 0) if has_vest else (0, 0, 255)
                cv2.rectangle(frame, (vx1, vy1), (vx2, vy2), color, 2)

            # ---------- ALERT ----------
            missing = []
            if check_helmet and not has_helmet:
                missing.append("Helmet")
            if check_vest and not has_vest:
                missing.append("Vest")

            current_time = time.time()

            if missing:
                violation_key = (cam_id, person_id, tuple(sorted(missing)))

                if violation_key not in violation_tracker:
                    violation_tracker[violation_key] = {
                        "start_time": current_time,
                        "last_alert_time": 0
                    }

                entry = violation_tracker[violation_key]
                duration = current_time - entry["start_time"]

                if duration >= VIOLATION_THRESHOLD:
                    if current_time - entry["last_alert_time"] >= ALERT_COOLDOWN:
                        generate_alert(
                            camera_id=f"CAM_{cam_id}",
                            zone=zone,
                            person_id=person_id,
                            violation="Missing " + ", ".join(missing),
                            bbox=None,          
                            frame=frame,
                            frame_id=frame_id
                        )
                        entry["last_alert_time"] = current_time
            else:
                for key in list(violation_tracker.keys()):
                    if key[0] == cam_id and key[1] == person_id:
                        del violation_tracker[key]


        # ---------- STREAM ----------
        ret, buffer = cv2.imencode(".jpg", frame)
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
        )


@app.route('/')
def index():
    return render_template(
        'index.html',
        camera_zones=CAMERA_ZONES
    )

@app.route('/video/<int:cam_id>')
def video(cam_id):
    return Response(
        generate_frames(cam_id),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )
@app.route("/alerts")
def show_alerts():
    return render_template("alerts.html", alerts=alerts)

@app.route("/set_zone", methods=["POST"])
def set_zone():
    cam_id = int(request.form["camera_id"])
    zone = request.form["zone"]

    CAMERA_ZONES[cam_id] = zone
    return redirect(url_for("index"))




if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)

