import streamlit as st
import streamlit.components.v1 as components
import json
import time
import tempfile
from pathlib import Path

from mqtt_shared import get_mqtt_buffer, init_mqtt, MQTT_TOPIC_SNAPSHOT_REQUEST, MQTT_TOPIC_CONFIG

st.set_page_config(page_title="Ρύθμιση Θέσεων", page_icon="🗺️", layout="wide")
st.title("🗺️ Ρύθμιση Θέσεων Στάθμευσης")

# ------------------------------------------------------------------
# Custom component: καμβάς όπου κάνεις κλικ στις γωνίες κάθε θέσης.
# Μικρά σημεία, διακεκομμένη γραμμή που ακολουθεί το ποντίκι, και
# ολοκλήρωση θέσης με Enter / διπλό κλικ / δεξί κλικ / κουμπί.
# ------------------------------------------------------------------
_COMPONENT_HTML = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body { margin: 0; padding: 0; font-family: sans-serif; background: transparent; }
  #bar { display: flex; gap: 8px; margin-bottom: 6px; align-items: center; flex-wrap: wrap; }
  button { padding: 6px 12px; border: 1px solid #888; border-radius: 6px; background: #f4f4f4;
           color: #111; cursor: pointer; font-size: 14px; }
  button:hover { background: #e2e2e2; }
  canvas { display: block; cursor: crosshair; border: 1px solid #666; width: 100%; height: auto; }
  #info { font-size: 13px; opacity: 0.8; }
</style>
</head>
<body>
<div id="bar">
  <button id="finish">✅ Ολοκλήρωση θέσης</button>
  <button id="undo">↩️ Αναίρεση</button>
  <button id="clear">🗑️ Καθαρισμός όλων</button>
  <span id="info"></span>
</div>
<canvas id="c" tabindex="0"></canvas>

<script>
  const canvas = document.getElementById("c");
  const ctx = canvas.getContext("2d");
  const info = document.getElementById("info");

  let W = 960, H = 540;
  let img = null, imgSrc = null;
  let spots = [];      // ολοκληρωμένες θέσεις: [{points_perc: [[x, y], ...]}]
  let cur = [];        // σημεία της θέσης που σχεδιάζεται (σε pixels του καμβά)
  let mouse = null;
  let initialised = false;

  function send(type, data) {
    window.parent.postMessage(Object.assign({ isStreamlitMessage: true, type: type }, data), "*");
  }
  function sendValue() { send("streamlit:setComponentValue", { value: spots, dataType: "json" }); }
  function fitFrame() { send("streamlit:setFrameHeight", { height: document.body.scrollHeight + 8 }); }

  window.addEventListener("message", function (e) {
    if (!e.data || e.data.type !== "streamlit:render") return;
    const a = e.data.args || {};
    if (a.width && a.height && (a.width !== W || a.height !== H)) { W = a.width; H = a.height; }
    canvas.width = W; canvas.height = H;
    if (!initialised) {
      initialised = true;
      if (Array.isArray(a.initial_spots)) spots = a.initial_spots;
    }
    const th = e.data.theme;
    if (th && th.textColor) document.body.style.color = th.textColor;
    if (a.image && a.image !== imgSrc) {
      imgSrc = a.image;
      img = new Image();
      img.onload = function () { draw(); fitFrame(); };
      img.src = a.image;
    } else {
      draw(); fitFrame();
    }
  });

  function centroid(pts) {
    let sx = 0, sy = 0;
    pts.forEach(function (p) { sx += p[0]; sy += p[1]; });
    return [sx / pts.length, sy / pts.length];
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    if (img && img.complete) ctx.drawImage(img, 0, 0, W, H);

    // Ολοκληρωμένες θέσεις (κίτρινες)
    spots.forEach(function (s, i) {
      const pts = s.points_perc.map(function (p) { return [p[0] * W, p[1] * H]; });
      ctx.beginPath();
      pts.forEach(function (p, k) { k === 0 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1]); });
      ctx.closePath();
      ctx.fillStyle = "rgba(255, 212, 0, 0.18)";
      ctx.fill();
      ctx.lineWidth = 2;
      ctx.strokeStyle = "#ffd400";
      ctx.stroke();
      const c = centroid(pts);
      ctx.font = "bold 16px sans-serif";
      ctx.fillStyle = "#ffd400";
      ctx.strokeStyle = "#000";
      ctx.lineWidth = 3;
      ctx.strokeText(String(i + 1), c[0] - 5, c[1] + 5);
      ctx.fillText(String(i + 1), c[0] - 5, c[1] + 5);
    });

    // Τρέχουσα θέση (πράσινη) + γραμμή που ακολουθεί το ποντίκι
    if (cur.length > 0) {
      const preview = mouse ? cur.concat([mouse]) : cur.slice();
      if (preview.length >= 3) {
        ctx.beginPath();
        preview.forEach(function (p, k) { k === 0 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1]); });
        ctx.closePath();
        ctx.fillStyle = "rgba(0, 255, 100, 0.15)";
        ctx.fill();
      }
      ctx.lineWidth = 2;
      ctx.strokeStyle = "#00ff66";
      ctx.beginPath();
      cur.forEach(function (p, k) { k === 0 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1]); });
      ctx.stroke();
      if (mouse) {
        ctx.setLineDash([6, 4]);
        ctx.beginPath();
        ctx.moveTo(cur[cur.length - 1][0], cur[cur.length - 1][1]);
        ctx.lineTo(mouse[0], mouse[1]);
        if (cur.length >= 2) ctx.lineTo(cur[0][0], cur[0][1]);
        ctx.stroke();
        ctx.setLineDash([]);
      }
      cur.forEach(function (p, k) {
        ctx.beginPath();
        ctx.arc(p[0], p[1], k === 0 ? 4 : 3, 0, Math.PI * 2);
        ctx.fillStyle = k === 0 ? "#ff3b3b" : "#00ff66";
        ctx.fill();
        ctx.lineWidth = 1;
        ctx.strokeStyle = "#000";
        ctx.stroke();
      });
    }
    info.textContent = "Θέσεις: " + spots.length + (cur.length ? " | Τρέχουσα: " + cur.length + " σημεία" : "");
  }

  function pos(e) {
    const r = canvas.getBoundingClientRect();
    return [(e.clientX - r.left) * W / r.width, (e.clientY - r.top) * H / r.height];
  }

  function finish() {
    if (cur.length < 3) { info.textContent = "Χρειάζονται τουλάχιστον 3 σημεία (έχεις " + cur.length + ")."; return; }
    spots.push({ points_perc: cur.map(function (p) { return [p[0] / W, p[1] / H]; }) });
    cur = [];
    sendValue();
    draw();
  }
  function undo() {
    if (cur.length) cur.pop();
    else if (spots.length) { spots.pop(); sendValue(); }
    draw();
  }
  function clearAll() { cur = []; spots = []; sendValue(); draw(); }

  canvas.addEventListener("mousemove", function (e) { mouse = pos(e); draw(); });
  canvas.addEventListener("mouseleave", function () { mouse = null; draw(); });
  canvas.addEventListener("click", function (e) { cur.push(pos(e)); canvas.focus(); draw(); });
  canvas.addEventListener("dblclick", function () {
    cur.pop();            // το 2ο κλικ του διπλού κλικ είναι διπλότυπο
    finish();
  });
  canvas.addEventListener("contextmenu", function (e) { e.preventDefault(); finish(); });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); finish(); }
    else if (e.key === "Backspace" || (e.ctrlKey && e.key.toLowerCase() === "z")) { e.preventDefault(); undo(); }
    else if (e.key === "Escape") { cur = []; draw(); }
  });
  document.getElementById("finish").addEventListener("click", finish);
  document.getElementById("undo").addEventListener("click", undo);
  document.getElementById("clear").addEventListener("click", clearAll);
  window.addEventListener("resize", fitFrame);

  send("streamlit:componentReady", { apiVersion: 1 });
</script>
</body>
</html>
"""


@st.cache_resource
def get_spot_drawer():
    folder = Path(tempfile.gettempdir()) / "spot_drawer_component_v1"
    folder.mkdir(exist_ok=True)
    (folder / "index.html").write_text(_COMPONENT_HTML, encoding="utf-8")
    return components.declare_component("spot_drawer", path=str(folder))


spot_drawer = get_spot_drawer()

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
