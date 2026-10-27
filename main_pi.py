"""
Smart Parking Management System - Edge AI Node (Raspberry Pi 5, HEADLESS)
Διπλωματική Εργασία: Ensemble Learning YOLO, MQTT Επικοινωνία & LLM Interface

Έκδοση για το Raspberry Pi, χωρίς οθόνη (headless, μέσω SSH):
  - Διαβάζει βίντεο από USB webcam (cv2.VideoCapture) αντί για αρχείο video.
  - ΔΕΝ χρησιμοποιεί cv2.imshow / cv2.waitKey / cv2.selectROIs (απαιτούν GUI/οθόνη).
  - Οι θέσεις στάθμευσης έρχονται ΑΠΟΚΛΕΙΣΤΙΚΑ από τη web σελίδα "Ρύθμιση Θέσεων"
    μέσω MQTT (δεν υπάρχει πλέον τοπικό fallback με το ποντίκι, αφού δεν υπάρχει οθόνη).
  - Σταματάει με Ctrl+C (KeyboardInterrupt) στο terminal του SSH.
"""

from ultralytics import YOLO
import cv2
import numpy as np
import base64
import json
import os
import threading
import paho.mqtt.client as mqtt
import time
import random

# ==========================================
# 0. ΡΥΘΜΙΣΕΙΣ ΕΠΙΚΟΙΝΩΝΙΑΣ (MQTT BROKER)
# ==========================================
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC_STATUS = "parking/diplomatiki/status/stel"
MQTT_TOPIC_CONFIG = "parking/diplomatiki/config/stel"  # ίδιο topic με mqtt_shared.py
MQTT_TOPIC_SNAPSHOT_REQUEST = "parking/diplomatiki/snapshot/request/stel"
MQTT_TOPIC_SNAPSHOT_RESPONSE = "parking/diplomatiki/snapshot/response/stel"

snapshot_requested = threading.Event()  # ανεβαίνει όταν η web σελίδα ζητήσει φρέσκο frame

print("Σύνδεση στον MQTT Broker...")

SPOTS_FILE = "spots.json"
spots_lock = threading.Lock()
parking_spots = []  # λίστα από {"points_perc": [[x, y], ...]}


def normalize_spot(raw_spot):
    """Ενιαία μορφή polygon {"points_perc": [[x, y], ...]}· μετατρέπει και το
    παλιό rectangle format (x_start_perc κλπ.) αν υπάρχει σε κάποιο παλιό αρχείο."""
    if "points_perc" in raw_spot:
        return {"points_perc": raw_spot["points_perc"]}
    if "x_start_perc" in raw_spot:
        x1, y1 = raw_spot["x_start_perc"], raw_spot["y_start_perc"]
        x2, y2 = raw_spot["x_end_perc"], raw_spot["y_end_perc"]
        return {"points_perc": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]}
    raise ValueError(f"Άγνωστη μορφή θέσης: {raw_spot}")


def save_spots_to_disk():
    with spots_lock:
        snapshot = list(parking_spots)
    with open(SPOTS_FILE, "w") as f:
        json.dump(snapshot, f)


def load_spots_from_disk():
    global parking_spots
    if os.path.exists(SPOTS_FILE):
        with open(SPOTS_FILE, "r") as f:
            raw = json.load(f)
        normalized = [normalize_spot(s) for s in raw]
        with spots_lock:
            parking_spots = normalized
        print(f"📂 Φορτώθηκαν {len(normalized)} θέσεις από το {SPOTS_FILE}.")
    else:
        with spots_lock:
            parking_spots = []
        print("📂 Δεν βρέθηκε spots.json ακόμα — περιμένω ρυθμίσεις από τη web σελίδα...")


my_client_id = f"edge_pi_{random.randint(1000, 99999)}"


def on_connect(client, userdata, flags, rc, *args):
    print("✅ Επιτυχής σύνδεση στο MQTT!")
    client.subscribe(MQTT_TOPIC_CONFIG, qos=1)
    client.subscribe(MQTT_TOPIC_SNAPSHOT_REQUEST, qos=1)
    print(f"👂 Έγινε subscribe στο {MQTT_TOPIC_CONFIG} (θέσεις) και στο {MQTT_TOPIC_SNAPSHOT_REQUEST} (αιτήματα frame)")


def on_message(client, userdata, msg):
    global parking_spots
    if msg.topic == MQTT_TOPIC_SNAPSHOT_REQUEST:
        print("📸 Ζητήθηκε νέο frame από τη web σελίδα.")
        snapshot_requested.set()
    elif msg.topic == MQTT_TOPIC_CONFIG:
        try:
            raw = json.loads(msg.payload.decode("utf-8"))
            new_spots = [normalize_spot(s) for s in raw]
            with spots_lock:
                parking_spots = new_spots
            save_spots_to_disk()
            print(f"📥 Νέες θέσεις από τη web σελίδα: {len(new_spots)} θέσεις αποθηκεύτηκαν στο {SPOTS_FILE}.")
        except Exception as e:
            print(f"❌ Σφάλμα επεξεργασίας config από MQTT: {e}")


try:
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=my_client_id)
except AttributeError:
    mqtt_client = mqtt.Client(client_id=my_client_id)

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

try:
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT)
    mqtt_client.loop_start()
except Exception as e:
    print(f"❌ Αποτυχία σύνδεσης στο MQTT: {e}")

last_sent_time = 0

# ==========================================
# 1. ΦΟΡΤΩΣΗ ΜΟΝΤΕΛΩΝ ΜΗΧΑΝΙΚΗΣ ΜΑΘΗΣΗΣ
# ==========================================
print("Φόρτωση Ensemble Μοντέλων...")
model_nano = YOLO('yolov8n.pt')
model_small = YOLO('yolov8m.pt')

# ==========================================
# 2. ΡΥΘΜΙΣΕΙΣ ΚΑΜΕΡΑΣ (USB WEBCAM)
# ==========================================
CAMERA_INDEX = 0  # Άλλαξέ το σε 1, 2 κλπ. αν το 0 δεν δείξει την κάμερά σου
WIDTH = 1280
HEIGHT = 720
FRAME_SKIP = 30
frame_count = 0
spot_states = []

cap = cv2.VideoCapture(CAMERA_INDEX)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)

if not cap.isOpened():
    print(f"❌ Δεν μπόρεσα να ανοίξω την κάμερα στο index {CAMERA_INDEX}. "
          f"Δοκίμασε άλλο index (1, 2, ...) ή έλεγξε με 'ls /dev/video*'.")
    exit()

# ==========================================
# 3. ΑΡΧΙΚΟΠΟΙΗΣΗ (SETUP)
# ==========================================
success, frame = cap.read()
if not success:
    print("❌ Δεν μπόρεσα να διαβάσω frame από την κάμερα.")
    exit()
frame = cv2.resize(frame, (WIDTH, HEIGHT))

load_spots_from_disk()
print("🚀 Ξεκινά ο βρόχος ανίχνευσης. Πάτα Ctrl+C για να σταματήσεις.")

# ==========================================
# 4. ΚΥΡΙΟΣ ΒΡΟΧΟΣ ΕΚΤΕΛΕΣΗΣ (MAIN LOOP)
# ==========================================
try:
    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            print("⚠️ Αποτυχία ανάγνωσης frame — επανάληψη...")
            continue

        frame = cv2.resize(frame, (WIDTH, HEIGHT))
        h_curr, w_curr = frame.shape[:2]
        frame_count += 1

        # --- Απάντηση σε αίτημα φρέσκου frame (για τη σελίδα "Ρύθμιση Θέσεων") ---
        if snapshot_requested.is_set():
            snapshot_requested.clear()
            ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ok:
                b64 = base64.b64encode(jpg.tobytes()).decode("utf-8")
                mqtt_client.publish(MQTT_TOPIC_SNAPSHOT_RESPONSE, b64, qos=1)
                print(f"📤 Στάλθηκε snapshot ({len(b64) // 1024} KB)")

        with spots_lock:
            spots_snapshot = list(parking_spots)

        if len(spot_states) != len(spots_snapshot):
            spot_states = [False] * len(spots_snapshot)

        current_polys = []
        for spot in spots_snapshot:
            pts = [(int(px * w_curr), int(py * h_curr)) for px, py in spot["points_perc"]]
            current_polys.append(np.array(pts, dtype=np.int32))

        # --- Μηχανισμός Εξοικονόμησης Πόρων & YOLO ---
        if frame_count % FRAME_SKIP == 0:
            yolo_detections = [False] * len(spots_snapshot)

            results_n = model_nano.predict(frame, conf=0.25, verbose=False)
            results_s = model_small.predict(frame, conf=0.42, verbose=False)

            all_detected_boxes = []
            for r in results_n:
                for box in r.boxes.xyxy.cpu().numpy(): all_detected_boxes.append(box)
            for r in results_s:
                for box in r.boxes.xyxy.cpu().numpy(): all_detected_boxes.append(box)

            for box in all_detected_boxes:
                x1, y1, x2, y2 = box
                box_width = x2 - x1
                box_height = y2 - y1

                if box_width < 30 or box_height < 30 or box_width > 350 or box_height > 350:
                    continue

                car_center_x = x1 + (box_width / 2)
                car_center_y = y1 + (box_height / 2)

                for index, poly in enumerate(current_polys):
                    if yolo_detections[index]: continue
                    inside = cv2.pointPolygonTest(poly, (float(car_center_x), float(car_center_y)), False)
                    if inside >= 0:
                        yolo_detections[index] = True

            spot_states = yolo_detections

        # --- Δημιουργία και Αποστολή MQTT Πακέτου (με Heartbeat) ---
        current_time = time.time()
        is_yolo_frame = (frame_count % FRAME_SKIP == 0)
        time_elapsed = (current_time - last_sent_time > 10)

        if spots_snapshot and (is_yolo_frame or time_elapsed):
            payload_dict = {}
            for idx, state in enumerate(spot_states):
                spot_id = f"spot_{idx + 1}"
                payload_dict[spot_id] = "Taken" if state else "Free"

            json_payload = json.dumps(payload_dict)
            mqtt_client.publish(MQTT_TOPIC_STATUS, json_payload, qos=1, retain=True)
            last_sent_time = current_time

            reason = "YOLO update" if is_yolo_frame else "Heartbeat (10s)"
            print(f"📤 Published ({reason}): {json_payload}")

except KeyboardInterrupt:
    print("\n⏹️  Διακοπή από χρήστη (Ctrl+C)...")

# ==========================================
# 5. ΑΣΦΑΛΗΣ ΤΕΡΜΑΤΙΣΜΟΣ ΠΡΟΓΡΑΜΜΑΤΟΣ
# ==========================================
cap.release()
mqtt_client.loop_stop()
mqtt_client.disconnect()
print("Το πρόγραμμα τερματίστηκε. Αποσύνδεση από MQTT επιτυχής.")
