import streamlit as st
import json
import time

from mqtt_shared import get_mqtt_buffer, init_mqtt, MQTT_TOPIC_SNAPSHOT_REQUEST, MQTT_TOPIC_CONFIG

st.set_page_config(page_title="Ρύθμιση Θέσεων", page_icon="🗺️", layout="wide")
st.title("🗺️ Ρύθμιση Θέσεων Στάθμευσης")

if not st.session_state.get("setup_ok"):
    pw = st.text_input("Κωδικός πρόσβασης", type="password")
    if pw:
        if pw == st.secrets["SETUP_PASSWORD"]:
            st.session_state.setup_ok = True
            st.rerun()
        else:
            st.error("Λάθος κωδικός.")
    st.stop()

# Καμβάς σχεδίασης: ο νέος (v2) δεν χρησιμοποιεί iframe ούτε στατικό αρχείο από τον server·
# ο παλιός (v1) μένει ως εναλλακτική και φορτώνεται μόνο αν τον ζητήσεις.
try:
    from spot_drawer_v2 import spot_drawer as spot_drawer_v2
except Exception:
    spot_drawer_v2 = None

mqtt_buffer = get_mqtt_buffer()
mqtt_client = init_mqtt()

if "spots_in_progress" not in st.session_state:
    st.session_state.spots_in_progress = []

# Μετά από refresh φορτώνουμε τις θέσεις που έχουν ήδη σταλεί στο Pi
# (είναι retained μήνυμα στο broker και τις λαμβάνει το mqtt_shared.py).
if not st.session_state.get("spots_loaded") and mqtt_buffer.get("config") is not None:
    st.session_state.spots_in_progress = mqtt_buffer["config"]
    st.session_state.spots_loaded = True

CANVAS_W, CANVAS_H = 960, 540  # ίδιος λόγος διαστάσεων με το WIDTH=1280/HEIGHT=720 του Pi

st.markdown(
    "**Οδηγίες:** 1) «Λήψη νέου frame». 2) Κλικάρισε τις γωνίες της θέσης στη σειρά (τουλάχιστον 3). "
    "3) Ολοκλήρωση με **Enter**, **διπλό κλικ** ή **δεξί κλικ**. 4) Επανέλαβε για κάθε θέση. "
    "5) «Αποστολή στο Pi». — **Backspace**: αναίρεση, **Esc**: ακύρωση τρέχουσας θέσης."
)

use_v1 = st.toggle(
    "Εναλλακτικός καμβάς (iframe)",
    value=spot_drawer_v2 is None,
    help="Άλλαξέ το αν ο καμβάς δεν εμφανίζεται.",
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
                    st.rerun()
            else:
                st.warning("Δεν ήρθε frame μέσα σε 15 δευτερόλεπτα. Έλεγξε ότι τρέχει το main_pi.py.")

with c2:
    send_slot = st.empty()  # το κουμπί αποστολής μπαίνει εδώ, αφού ξέρουμε πόσες θέσεις υπάρχουν

snapshot_b64 = mqtt_buffer.get("snapshot_b64")
if not snapshot_b64:
    st.warning("⏳ Δεν έχει ληφθεί ακόμα frame. Πάτα «Λήψη νέου frame».")
    st.stop()

if use_v1 or spot_drawer_v2 is None:
    try:
        from spot_drawer import spot_drawer as spot_drawer_v1
    except Exception:
        import traceback
        st.error("Σφάλμα φόρτωσης του εναλλακτικού καμβά (spot_drawer.py):")
        st.code(traceback.format_exc())
        st.stop()
    value = spot_drawer_v1(
        image="data:image/jpeg;base64," + snapshot_b64,
        width=CANVAS_W,
        height=CANVAS_H,
        initial_spots=st.session_state.spots_in_progress,
        key="spot_drawer",
        default=None,
    )
else:
    value = spot_drawer_v2(
        image="data:image/jpeg;base64," + snapshot_b64,
        width=CANVAS_W,
        height=CANVAS_H,
        initial_spots=st.session_state.spots_in_progress,
        key=f"spot_drawer_v2_{mqtt_buffer.get('snapshot_time')}",  # νέο frame -> νέος καμβάς
    )
if value is not None:
    st.session_state.spots_in_progress = value

st.write(f"**Καταγεγραμμένες θέσεις:** {len(st.session_state.spots_in_progress)}")

if st.session_state.spots_in_progress:
    send_clicked = send_slot.button("📤 Αποστολή στο Pi", type="primary", use_container_width=True)
else:
    send_clicked = False
    send_slot.caption("Σχεδίασε τουλάχιστον μία θέση για να εμφανιστεί η αποστολή.")

if send_clicked:
    spots = value if value is not None else st.session_state.spots_in_progress
    payload = json.dumps(spots, ensure_ascii=False)
    mqtt_client.publish(MQTT_TOPIC_CONFIG, payload, qos=1, retain=True)
    st.success(f"Στάλθηκαν {len(spots)} θέσεις στο Pi!")
