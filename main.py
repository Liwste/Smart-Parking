"""
Smart Parking Management System - Edge AI Node
Διπλωματική Εργασία: Ensemble Learning YOLO, MQTT Επικοινωνία & LLM Interface
Αυτό το script τρέχει στο Edge Node, αναλύει το βίντεο τοπικά, και στέλνει 
τα αποτελέσματα (Free/Taken) σε πραγματικό χρόνο στον MQTT Broker.
"""

from ultralytics import YOLO
import cv2
import json
import os
import paho.mqtt.client as mqtt
import time
import random

# ==========================================
# 0. ΡΥΘΜΙΣΕΙΣ ΕΠΙΚΟΙΝΩΝΙΑΣ (MQTT BROKER)
# ==========================================
MQTT_BROKER = "broker.hivemq.com" 
MQTT_PORT = 1883
MQTT_TOPIC = "parking/diplomatiki/status/stel"

print("Σύνδεση στον MQTT Broker...")

# Δημιουργία ΜΟΝΑΔΙΚΟΥ Client ID
my_client_id = f"edge_camera_{random.randint(1000, 99999)}"

# Ασφαλής αρχικοποίηση ανάλογα με την έκδοση του paho-mqtt
try:
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=my_client_id)
except AttributeError:
    mqtt_client = mqtt.Client(client_id=my_client_id)

try:
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT)
    mqtt_client.loop_start() 
    print("✅ Επιτυχής σύνδεση στο MQTT!")
except Exception as e:
    print(f"❌ Αποτυχία σύνδεσης στο MQTT: {e}")

last_sent_time = 0
# ==========================================
# 1. ΦΟΡΤΩΣΗ ΜΟΝΤΕΛΩΝ ΜΗΧΑΝΙΚΗΣ ΜΑΘΗΣΗΣ
# ==========================================
# Φορτώνουμε τα προεκπαιδευμένα μοντέλα YOLOv8. 
# Για την ώρα χρησιμοποιούμε το Small/Medium (yolov8m) που δίνει >90% ακρίβεια.
print("Φόρτωση Ensemble Μοντέλων...")
model_nano = YOLO('yolov8n.pt')  
model_small = YOLO('yolov8m.pt') 

# ==========================================
# 2. ΡΥΘΜΙΣΕΙΣ ΒΙΝΤΕΟ ΚΑΙ ΠΑΡΑΜΕΤΡΩΝ ΕΛΕΓΧΟΥ
# ==========================================
video_path = r"D:\Επιφάνεια Εργασίαςς\parking_test.mp4.mp4" 
cap = cv2.VideoCapture(video_path)

WIDTH = 1280
HEIGHT = 720
SPOTS_FILE = "spots.json" # Το αρχείο όπου αποθηκεύονται οι θέσεις που σχεδιάζουμε
FRAME_SKIP = 30  # Επεξεργαζόμαστε 1 frame κάθε 30 (περίπου 1 φορά το δευτερόλεπτο) για εξοικονόμηση πόρων
frame_count = 0
spot_states = [] 

# ==========================================
# 3. ΥΠΟΣΤΗΡΙΚΤΙΚΗ ΣΥΝΑΡΤΗΣΗ (ΓΡΑΦΙΚΟ ΠΕΡΙΒΑΛΛΟΝ)
# ==========================================
# Αυτή η συνάρτηση ανοίγει το βίντεο και μας επιτρέπει να ζωγραφίσουμε με 
# το ποντίκι τα "κουτιά" των θέσεων στάθμευσης αν δεν υπάρχουν ήδη.
def add_new_spots(frame, existing_spots, w_orig, h_orig):
    print("Λειτουργία Προσθήκης: Σύρε -> ENTER (για κάθε θέση) -> ESC (για τέλος).")
    rois = cv2.selectROIs("Setup Spots", frame, fromCenter=False, showCrosshair=True)
    cv2.destroyWindow("Setup Spots")

    for roi in rois:
        x, y, w, h = roi
        if w > 0 and h > 0: 
            # Αποθηκεύουμε τις θέσεις ως ποσοστά (%) ώστε να δουλεύουν σωστά
            # ακόμα κι αν αλλάξουμε την ανάλυση του βίντεο στο μέλλον.
            spot = {
                "x_start_perc": x / w_orig,
                "y_start_perc": y / h_orig,
                "x_end_perc": (x + w) / w_orig,
                "y_end_perc": (y + h) / h_orig
            }
            existing_spots.append(spot)
    
    # Αποθήκευση στο αρχείο JSON για να μην τα ζωγραφίζουμε κάθε φορά
    with open(SPOTS_FILE, 'w') as f:
        json.dump(existing_spots, f)
    return existing_spots

# ==========================================
# 4. ΑΡΧΙΚΟΠΟΙΗΣΗ (SETUP)
# ==========================================
success, frame = cap.read()
if not success: exit()
frame = cv2.resize(frame, (WIDTH, HEIGHT))
h_orig, w_orig = frame.shape[:2]

# Φόρτωση των θέσεων αν υπάρχουν, αλλιώς άνοιγμα του εργαλείου σχεδίασης
parking_spots = []
if os.path.exists(SPOTS_FILE):
    with open(SPOTS_FILE, 'r') as f:
        parking_spots = json.load(f)
else:
    parking_spots = add_new_spots(frame, parking_spots, w_orig, h_orig)

# ==========================================
# 5. ΚΥΡΙΟΣ ΒΡΟΧΟΣ ΕΚΤΕΛΕΣΗΣ (MAIN LOOP)
# ==========================================
while cap.isOpened():
    success, frame = cap.read()
    if not success: break

    frame = cv2.resize(frame, (WIDTH, HEIGHT))
    h_curr, w_curr = frame.shape[:2]
    frame_count += 1

    # Αρχικοποίηση λίστας καταστάσεων (όλες οι θέσεις ξεκινούν ως Free)
    if len(spot_states) != len(parking_spots):
        spot_states = [False] * len(parking_spots)

    # Μετατροπή των ποσοστών των θέσεων σε pixels για την τρέχουσα ανάλυση
    current_rects = []
    for spot in parking_spots:
        p1 = (int(spot["x_start_perc"] * w_curr), int(spot["y_start_perc"] * h_curr))
        p2 = (int(spot["x_end_perc"] * w_curr), int(spot["y_end_perc"] * h_curr))
        current_rects.append((p1, p2))

# --- 5.1 & 5.2 Μηχανισμός Εξοικονόμησης Πόρων & YOLO ---
    if frame_count % FRAME_SKIP == 0:
        yolo_detections = [False] * len(parking_spots)
        
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

            for index, (p1, p2) in enumerate(current_rects):
                if yolo_detections[index]: continue 
                
                rx1, ry1, rx2, ry2 = p1[0], p1[1], p2[0], p2[1]
                
                xA = max(x1, rx1)
                yA = max(y1, ry1)
                xB = min(x2, rx2)
                yB = min(y2, ry2)

                car_center_x = x1 + (box_width / 2)
                car_center_y = y1 + (box_height / 2)

                if rx1 <= car_center_x <= rx2 and ry1 <= car_center_y <= ry2:
                    yolo_detections[index] = True
                    
        spot_states = yolo_detections # Ενημέρωση της συνολικής λίστας καταστάσεων
        
    # --- 5.3 Δημιουργία και Αποστολή MQTT Πακέτου (με Heartbeat) ---
    current_time = time.time()
    
    is_yolo_frame = (frame_count % FRAME_SKIP == 0)
    time_elapsed = (current_time - last_sent_time > 10)

    if parking_spots and (is_yolo_frame or time_elapsed):
        payload_dict = {}
        for idx, state in enumerate(spot_states):
            spot_id = f"spot_{idx + 1}"
            payload_dict[spot_id] = "Taken" if state else "Free"
            
        json_payload = json.dumps(payload_dict)
        
        # ΠΡΟΣΟΧΗ: retain=False (ή απλά το σβήνουμε) στους public brokers!
        mqtt_client.publish(MQTT_TOPIC, json_payload,qos=1, retain=True)
        last_sent_time = current_time
        
        reason = "YOLO update" if is_yolo_frame else "Heartbeat (10s)"
        print(f"📤 Published ({reason}): {json_payload}")
        
    # ==========================================
    # 6. ΣΧΕΔΙΑΣΗ UI ΚΑΙ ΑΠΟΤΕΛΕΣΜΑΤΩΝ ΣΤΗΝ ΟΘΟΝΗ
    # ==========================================
    for index, (p1, p2) in enumerate(current_rects):
        is_occupied = spot_states[index]
        
        # Ορίζουμε το κείμενο (π.χ. "Spot 1") και το χρώμα ανάλογα με την κατάσταση
        label = f"Spot {index + 1}" 
        color = (0, 0, 255) if is_occupied else (0, 255, 0) # Κόκκινο (Taken) ή Πράσινο (Free)

        # Ζωγραφίζουμε το κουτί της θέσης
        cv2.rectangle(frame, p1, p2, color, 2)
        # Υπολογίζουμε το μέγεθος του κειμένου για να φτιάξουμε το "ταμπελάκι" από πάνω
        (w_txt, h_txt), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
        # Ζωγραφίζουμε το φόντο για το κείμενο
        cv2.rectangle(frame, (p1[0], p1[1] - 20), (p1[0] + w_txt, p1[1]), color, -1)
        # Γράφουμε τον αριθμό της θέσης
        cv2.putText(frame, label, (p1[0], p1[1] - 5), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

    # Εμφάνιση του τελικού αποτελέσματος στο χρήστη (Τοπική Οθόνη)
    cv2.imshow("Smart Parking Edge AI - YOLO Voting Ensemble", frame)
    
    # Χειρισμός πλήκτρων
    key = cv2.waitKey(1) & 0xFF
    if key == 27 or key == ord('q'): break # ESC ή 'q' για έξοδο
    elif key == ord('a'): # 'a' για προσθήκη νέων θέσεων
        parking_spots = add_new_spots(frame, parking_spots, w_curr, h_curr)
    elif key == ord('c'): # 'c' για διαγραφή (clear) όλων των θέσεων
        parking_spots, spot_states = [], []
        if os.path.exists(SPOTS_FILE): os.remove(SPOTS_FILE)

# ==========================================
# 7. ΑΣΦΑΛΗΣ ΤΕΡΜΑΤΙΣΜΟΣ ΠΡΟΓΡΑΜΜΑΤΟΣ
# ==========================================
# Απελευθερώνουμε τη μνήμη και κλείνουμε σωστά τη σύνδεση με το Internet (MQTT)
cap.release()
cv2.destroyAllWindows()
mqtt_client.loop_stop()
mqtt_client.disconnect()
print("Το πρόγραμμα τερματίστηκε. Αποσύνδεση από MQTT επιτυχής.")
