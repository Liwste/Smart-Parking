import streamlit as st
import json
import time
import base64
import io
from PIL import Image, ImageDraw
from streamlit_drawable_canvas import st_canvas

from mqtt_shared import get_mqtt_buffer, init_mqtt, MQTT_TOPIC_SNAPSHOT_REQUEST, MQTT_TOPIC_CONFIG

st.set_page_config(page_title="Ρύθμιση Θέσεων", page_icon="🗺️", layout="wide")
st.title("🗺️ Ρύθμιση Θέσεων Στάθμευσης")

mqtt_buffer = get_mqtt_buffer()
mqtt_client = init_mqtt()

if "spots_in_progress" not in st.session_state:
    st.session_state.spots_in_progress = []
if "canvas_key_counter" not in st.session_state:
    st.session_state.canvas_key_counter = 0

CANVAS_W, CANVAS_H = 960, 540  # ίδιος λόγος διαστάσεων με το WIDTH=1280/HEIGHT=720 του Pi

st.markdown(
    "**Οδηγίες:** 1) Ζήτα φρέσκο frame. 2) Κλικάρε τις γωνίες της τρέχουσας θέσης στη σειρά "
    "(τουλάχιστον 3). 3) «Ολοκλήρωση θέσης». 4) Επανέλαβε. 5) «Αποστολή στο Pi» στο τέλος."
)

c1, c2, c3, c4 = st.columns(4)
with c1:
    if st.button("📷 Λήψη νέου frame", use_container_width=True):
        mqtt_client.publish(MQTT_TOPIC_SNAPSHOT_REQUEST, "request", qos=1)
        st.toast("Στάλθηκε αίτημα frame στο Pi...")

with c2:
    finish_clicked = st.button("✅ Ολοκλήρωση θέσης", use_container_width=True)

with c3:
    if st.button("↩️ Αναίρεση τελευταίας", use_container_width=True):
        if st.session_state.spots_in_progress:
            st.session_state.spots_in_progress.pop()
        st.session_state.canvas_key_counter += 1

with c4:
    if st.button("🗑️ Καθαρισμός όλων", use_container_width=True):
        st.session_state.spots_in_progress = []
        st.session_state.canvas_key_counter += 1

st.write(f"**Καταγεγραμμένες θέσεις:** {len(st.session_state.spots_in_progress)}")

snapshot_b64 = mqtt_buffer.get("snapshot_b64")
if not snapshot_b64:
    st.warning("⏳ Δεν έχει ληφθεί ακόμα frame. Πάτα «Λήψη νέου frame».")
    st.stop()

img_bytes = base64.b64decode(snapshot_b64)
base_image = Image.open(io.BytesIO(img_bytes)).convert("RGB").resize((CANVAS_W, CANVAS_H))

# Ζωγραφίζουμε τις ήδη ολοκληρωμένες θέσεις πάνω στην εικόνα, για αναφορά
overlay = base_image.copy()
draw = ImageDraw.Draw(overlay)
for i, spot in enumerate(st.session_state.spots_in_progress):
    pts = [(px * CANVAS_W, py * CANVAS_H) for px, py in spot["points_perc"]]
    draw.polygon(pts, outline=(255, 255, 0), width=2)
    cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    draw.text((cx, cy), str(i + 1), fill=(255, 255, 0))

canvas_result = st_canvas(
    fill_color="rgba(0, 255, 0, 0.3)",
    stroke_width=2,
    stroke_color="#00FF00",
    background_image=overlay,
    update_streamlit=True,
    height=CANVAS_H,
    width=CANVAS_W,
    drawing_mode="point",
    point_display_radius=5,
    key=f"canvas_{st.session_state.canvas_key_counter}",
)

if finish_clicked:
    points = []
    if canvas_result.json_data is not None:
        for obj in canvas_result.json_data["objects"]:
            if obj.get("type") == "circle":
                points.append((obj["left"], obj["top"]))

    if len(points) < 3:
        st.error("Χρειάζονται τουλάχιστον 3 σημεία. Κλικάρισε πρώτα τις γωνίες στον καμβά.")
    else:
        points_perc = [[x / CANVAS_W, y / CANVAS_H] for x, y in points]
        st.session_state.spots_in_progress.append({"points_perc": points_perc})
        st.session_state.canvas_key_counter += 1
        st.rerun()

st.divider()

if st.button(
    "📤 Αποστολή στο Pi",
    type="primary",
    disabled=len(st.session_state.spots_in_progress) == 0,
):
    payload = json.dumps(st.session_state.spots_in_progress, ensure_ascii=False)
    mqtt_client.publish(MQTT_TOPIC_CONFIG, payload, qos=1, retain=True)
    st.success(f"Στάλθηκαν {len(st.session_state.spots_in_progress)} θέσεις στο Pi!")