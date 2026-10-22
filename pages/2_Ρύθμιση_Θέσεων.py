import streamlit as st
import json
import time

from mqtt_shared import get_mqtt_buffer, init_mqtt, MQTT_TOPIC_SNAPSHOT_REQUEST, MQTT_TOPIC_CONFIG

st.set_page_config(page_title="Ρύθμιση Θέσεων", page_icon="🗺️", layout="wide")
st.title("🗺️ Ρύθμιση Θέσεων Στάθμευσης")

try:
    from spot_drawer import spot_drawer
except Exception:
    import traceback
    st.error("Σφάλμα φόρτωσης του spot_drawer.py — στείλε μου αυτό το μήνυμα:")
    st.code(traceback.format_exc())
    st.stop()

mqtt_buffer = get_mqtt_buffer()
mqtt_client = init_mqtt()

if "spots_in_progress" not in st.session_state:
    st.session_state.spots_in_progress = []

CANVAS_W, CANVAS_H = 960, 540  # ίδιος λόγος διαστάσεων με το WIDTH=1280/HEIGHT=720 του Pi

st.markdown(
    "**Οδηγίες:** 1) «Λήψη νέου frame». 2) Κλικάρισε τις γωνίες της θέσης στη σειρά (τουλάχιστον 3). "
    "3) Ολοκλήρωση με **Enter**, **διπλό κλικ** ή **δεξί κλικ**. 4) Επανέλαβε για κάθε θέση. "
    "5) «Αποστολή στο Pi». — **Backspace**: αναίρεση, **Esc**: ακύρωση τρέχουσας θέσης."
)

c1, c2 = st.columns([1, 1])
with c1:
    if st.button("📷 Λήψη νέου frame", use_container_width=True):
        old_b64 = mqtt_buffer.get("snapshot_b64")
        old_time = mqtt_buffer.get("snapshot_time")
        mqtt_client.publish(MQTT_TOPIC_SNAPSHOT_REQUEST, "request", qos=1)
        # Περιμένουμε (έως ~15s) το νέο frame και ανανεώνουμε αυτόματα τη σελίδα
        with st.spinner("Αναμονή frame από το Pi..."):
            for _ in range(30):
                time.sleep(0.5)
                if (mqtt_buffer.get("snapshot_time") != old_time
                        or mqtt_buffer.get("snapshot_b64") != old_b64):
                    break
            else:
                st.warning("Δεν ήρθε frame μέσα σε 15 δευτερόλεπτα. Έλεγξε ότι τρέχει το main_pi.py.")
        st.rerun()

with c2:
    send_clicked = st.button(
        "📤 Αποστολή στο Pi",
        type="primary",
        use_container_width=True,
        disabled=len(st.session_state.spots_in_progress) == 0,
    )

snapshot_b64 = mqtt_buffer.get("snapshot_b64")
if not snapshot_b64:
    st.warning("⏳ Δεν έχει ληφθεί ακόμα frame. Πάτα «Λήψη νέου frame».")
    st.stop()

value = spot_drawer(
    image="data:image/jpeg;base64," + snapshot_b64,
    width=CANVAS_W,
    height=CANVAS_H,
    initial_spots=st.session_state.spots_in_progress,
    key="spot_drawer",
    default=None,
)
if value is not None:
    st.session_state.spots_in_progress = value

st.write(f"**Καταγεγραμμένες θέσεις:** {len(st.session_state.spots_in_progress)}")

if send_clicked:
    spots = value if value is not None else st.session_state.spots_in_progress
    payload = json.dumps(spots, ensure_ascii=False)
    mqtt_client.publish(MQTT_TOPIC_CONFIG, payload, qos=1, retain=True)
    st.success(f"Στάλθηκαν {len(spots)} θέσεις στο Pi!")
