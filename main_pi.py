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
import socket
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
MQTT_TOPIC_AVAILABILITY = "parking/diplomatiki/availability/stel"

# Δίκτυα με IPv6/NAT64 (π.χ. hotspot iPhone): η σύνδεση MQTT πάνω από NAT64 κόβεται
# (connection reset) αμέσως μετά το TCP handshake. Χρησιμοποιούμε μόνο IPv4.
_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)


socket.getaddrinfo = _ipv4_only_getaddrinfo

snapshot_requested = threading.Event()  # ανεβαίνει όταν η web σελίδα ζητήσει φρέσκο frame

print("Σύνδεση στον MQTT Broker...")

SPOTS_FILE = "spots.json"
spots_lock = threading.Lock()
parking_spots = []  # λίστα από {"points_perc": [[x, y], ...]}


def normalize_spot(raw_spot):
    """Ενιαία μορφή polygon {"points_perc": [[x, y], ...]}· μετατρέπει και το
    παλιό rectangle format (x_start_perc κλπ.) αν υπάρχει σε κάποιο παλιό αρχείο."""
    if not isinstance(raw_spot, dict):
        raise ValueError(f"Άγνωστη μορφή θέσης: {raw_spot}")
    if "points_perc" in raw_spot:
        pts = raw_spot["points_perc"]
    elif "x_start_perc" in raw_spot:
        x1, y1 = raw_spot["x_start_perc"], raw_spot["y_start_perc"]
        x2, y2 = raw_spot["x_end_perc"], raw_spot["y_end_perc"]
        pts = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
    else:
        raise ValueError(f"Άγνωστη μορφή θέσης: {raw_spot}")
    ok = isinstance(pts, list) and 3 <= len(pts) <= 32 and all(
        isinstance(p, list) and len(p) == 2
        and all(isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1 for v in p)
        for p in pts)
    if not ok:
        raise ValueError("Μη έγκυρα σημεία θέσης")
    return {"points_perc": pts}


def save_spots_to_disk():
    with spots_lock:
        snapshot = list(parking_spots)
    tmp_file = SPOTS_FILE + ".tmp"
    with open(tmp_file, "w") as f:
        json.dump(snapshot, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_file, SPOTS_FILE)


def load_spots_from_disk():
    global parking_spots
    if os.path.exists(SPOTS_FILE):
        try:
            with open(SPOTS_FILE, "r") as f:
                raw = json.load(f)
            normalized = [normalize_spot(s) for s in raw]
        except Exception as e:
            bad_file = SPOTS_FILE + ".corrupt"
            os.replace(SPOTS_FILE, bad_file)
            print(f"⚠️ Το {SPOTS_FILE} ήταν χαλασμένο ({e}). Μετονομάστηκε σε {bad_file}.")
            normalized = []
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
    client.publish(MQTT_TOPIC_AVAILABILITY, "online", qos=1, retain=True)
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
mqtt_client.will_set(MQTT_TOPIC_AVAILABILITY, "offline", qos=1, retain=True)

try:
    mqtt_client.reconnect_delay_set(min_delay=1, max_delay=60)
    mqtt_client.connect_async(MQTT_BROKER, MQTT_PORT, keepalive=30)
    mqtt_client.loop_start()
except Exception as e:
    print(f"❌ Αποτυχία σύνδεσης στο MQTT: {e}")

last_sent_time = 0

# ==========================================
# 1. ΦΟΡΤΩΣΗ ΜΟΝΤΕΛΩΝ ΜΗΧΑΝΙΚΗΣ ΜΑΘΗΣΗΣ
# ==========================================
print("Φόρτωση Ensemble Μοντέλων...")
model_nano = YOLO('yolov8n.pt')
model_medium = YOLO('yolov8m.pt')


# --- Ρυθμίσεις ανίχνευσης (weighted voting ensemble) ---
USE_CLAHE = True            # εξισορρόπηση φωτισμού πριν το inference
USE_SHADOW_CHECK = True     # αγνόηση ανιχνεύσεων που μοιάζουν με σκιά
CONF_NANO = 0.25            # κατώφλι εμπιστοσύνης YOLOv8n
CONF_MEDIUM = 0.42          # κατώφλι εμπιστοσύνης YOLOv8m
MODEL_WEIGHTS = {"nano": 0.4, "medium": 0.6}   # βάρος κάθε μοντέλου στην ψηφοφορία
VOTE_THRESHOLD = 0.5        # άθροισμα ψήφων από το οποίο μια θέση θεωρείται Taken


def apply_clahe(frame):
    """Εξισορρόπηση φωτισμού (CLAHE) μόνο στο κανάλι φωτεινότητας L του χώρου LAB."""
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_eq = clahe.apply(l)
    return cv2.cvtColor(cv2.merge((l_eq, a, b)), cv2.COLOR_LAB2BGR)


def is_likely_shadow(frame, x1, y1, x2, y2, edge_density_threshold=0.02):
    """Οι σκιές έχουν λίγες ακμές (Canny) σε σχέση με ένα πραγματικό όχημα."""
    x1, y1, x2, y2 = map(int, [x1, y1, x2, y2])
    roi = frame[max(y1, 0):y2, max(x1, 0):x2]
    if roi.size == 0:
        return False
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    return cv2.countNonZero(edges) / edges.size < edge_density_threshold


def register_votes(results, weight, vote_scores, polys, frame):
    """Κάθε μοντέλο ψηφίζει το πολύ μία φορά ανά θέση (το βάρος του προστίθεται στη θέση
    όπου πέφτει το κέντρο μιας ανίχνευσης)."""
    voted = set()
    for r in results:
        for box in r.boxes.xyxy.cpu().numpy():
            x1, y1, x2, y2 = box
            box_width, box_height = x2 - x1, y2 - y1
            if box_width < 30 or box_height < 30 or box_width > 350 or box_height > 350:
                continue
            center = (float(x1 + box_width / 2), float(y1 + box_height / 2))
            for index, poly in enumerate(polys):
                if cv2.pointPolygonTest(poly, center, False) >= 0:
                    if index not in voted and not (USE_SHADOW_CHECK and is_likely_shadow(frame, x1, y1, x2, y2)):
                        vote_scores[index] += weight
                        voted.add(index)
                    break

# ==========================================
# 2. ΡΥΘΜΙΣΕΙΣ ΚΑΜΕΡΑΣ (USB WEBCAM)
# ==========================================
CAMERA_INDEX = 0  # Άλλαξέ το σε 1, 2 κλπ. αν το 0 δεν δείξει την κάμερά σου
WIDTH = 1280
HEIGHT = 720
FRAME_SKIP = 15
frame_count = 0
spot_states = []
CONFIRM_TAKEN = 2   # διαδοχικές ανιχνεύσεις για Free -> Taken
CONFIRM_FREE = 3    # διαδοχικές ανιχνεύσεις για Taken -> Free
change_counts = []        # πόσες διαδοχικές φορές η ανίχνευση διαφωνεί με την τρέχουσα κατάσταση
awaiting_first = True     # μέχρι την πρώτη πραγματική ανίχνευση δεν δημοσιεύουμε

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
            time.sleep(0.5)
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
            change_counts = [0] * len(spots_snapshot)
            awaiting_first = True

        current_polys = []
        for spot in spots_snapshot:
            pts = [(int(px * w_curr), int(py * h_curr)) for px, py in spot["points_perc"]]
            current_polys.append(np.array(pts, dtype=np.int32))

        # --- Μηχανισμός Εξοικονόμησης Πόρων & YOLO ---
        if frame_count % FRAME_SKIP == 0:
            vote_scores = [0.0] * len(spots_snapshot)
            frame_for_detection = apply_clahe(frame) if USE_CLAHE else frame

            t_start = time.monotonic()
            results_n = model_nano.predict(frame_for_detection, conf=CONF_NANO, verbose=False)
            results_m = model_medium.predict(frame_for_detection, conf=CONF_MEDIUM, verbose=False)
            t_infer = time.monotonic() - t_start

            register_votes(results_n, MODEL_WEIGHTS["nano"], vote_scores, current_polys, frame)
            register_votes(results_m, MODEL_WEIGHTS["medium"], vote_scores, current_polys, frame)

            yolo_detections = [score >= VOTE_THRESHOLD for score in vote_scores]
            print(f"⏱️ inference: {t_infer:.2f}s | votes: {[round(s, 1) for s in vote_scores]}")

            if awaiting_first:
                spot_states = yolo_detections
                awaiting_first = False
            else:
                for i, detected in enumerate(yolo_detections):
                    if detected == spot_states[i]:
                        change_counts[i] = 0
                    else:
                        change_counts[i] += 1
                        needed = CONFIRM_TAKEN if detected else CONFIRM_FREE
                        if change_counts[i] >= needed:
                            spot_states[i] = detected
                            change_counts[i] = 0

        # --- Δημιουργία και Αποστολή MQTT Πακέτου (με Heartbeat) ---
        current_time = time.time()
        is_yolo_frame = (frame_count % FRAME_SKIP == 0)
        time_elapsed = (current_time - last_sent_time > 10)

        if spots_snapshot and not awaiting_first and (is_yolo_frame or time_elapsed):
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
try:
    mqtt_client.publish(MQTT_TOPIC_AVAILABILITY, "offline", qos=1, retain=True).wait_for_publish(timeout=3)
except Exception:
    pass
mqtt_client.loop_stop()
mqtt_client.disconnect()
print("Το πρόγραμμα τερματίστηκε. Αποσύνδεση από MQTT επιτυχής.")
