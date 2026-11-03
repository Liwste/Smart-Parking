"""
Καμβάς σχεδίασης θέσεων στάθμευσης (polygons) ως Streamlit custom component v2.
Δεν τρέχει μέσα σε iframe και δεν χρειάζεται ξεχωριστό αίτημα για στατικό αρχείο·
όλος ο κώδικας ταξιδεύει μέσα στη σελίδα.
Κάνεις κλικ στις γωνίες κάθε θέσης και ολοκληρώνεις με Enter / διπλό κλικ / δεξί κλικ.
Επιστρέφει λίστα [{"points_perc": [[x, y], ...]}, ...] ή None αν δεν έχει αλλάξει τίποτα.
"""
import streamlit as st

_HTML = """
<div id="bar">
  <button id="finish">✅ Ολοκλήρωση θέσης</button>
  <button id="undo">↩️ Αναίρεση</button>
  <button id="clear">🗑️ Καθαρισμός όλων</button>
  <span id="info"></span>
</div>
<canvas id="c" tabindex="0"></canvas>
"""

_CSS = """
:host { display: block; font-family: sans-serif; }
#bar { display: flex; gap: 8px; margin-bottom: 6px; align-items: center; flex-wrap: wrap; }
button { padding: 6px 12px; border: 1px solid #888; border-radius: 6px; background: #f4f4f4;
         color: #111; cursor: pointer; font-size: 14px; }
button:hover { background: #e2e2e2; }
canvas { display: block; cursor: crosshair; border: 1px solid #666; width: 100%; height: auto; outline: none; }
#info { font-size: 13px; opacity: 0.8; }
"""

_JS = """
function centroid(pts) {
  let sx = 0, sy = 0;
  pts.forEach(function (p) { sx += p[0]; sy += p[1]; });
  return [sx / pts.length, sy / pts.length];
}

function draw(S) {
  const ctx = S.ctx, W = S.W, H = S.H;
  ctx.clearRect(0, 0, W, H);
  if (S.img && S.img.complete) ctx.drawImage(S.img, 0, 0, W, H);

  // Ολοκληρωμένες θέσεις (κίτρινες)
  S.spots.forEach(function (s, i) {
    const pts = s.points_perc.map(function (p) { return [p[0] * W, p[1] * H]; });
    ctx.beginPath();
    pts.forEach(function (p, k) { if (k === 0) ctx.moveTo(p[0], p[1]); else ctx.lineTo(p[0], p[1]); });
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
  const cur = S.cur;
  if (cur.length > 0) {
    const preview = S.mouse ? cur.concat([S.mouse]) : cur.slice();
    if (preview.length >= 3) {
      ctx.beginPath();
      preview.forEach(function (p, k) { if (k === 0) ctx.moveTo(p[0], p[1]); else ctx.lineTo(p[0], p[1]); });
      ctx.closePath();
      ctx.fillStyle = "rgba(0, 255, 100, 0.15)";
      ctx.fill();
    }
    ctx.lineWidth = 2;
    ctx.strokeStyle = "#00ff66";
    ctx.beginPath();
    cur.forEach(function (p, k) { if (k === 0) ctx.moveTo(p[0], p[1]); else ctx.lineTo(p[0], p[1]); });
    ctx.stroke();
    if (S.mouse) {
      ctx.setLineDash([6, 4]);
      ctx.beginPath();
      ctx.moveTo(cur[cur.length - 1][0], cur[cur.length - 1][1]);
      ctx.lineTo(S.mouse[0], S.mouse[1]);
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
  S.info.textContent = "Θέσεις: " + S.spots.length + (cur.length ? " | Τρέχουσα: " + cur.length + " σημεία" : "");
}

function sendValue(S) {
  S.setStateValue("spots", S.spots.map(function (s) { return { points_perc: s.points_perc }; }));
}

function pos(S, e) {
  const r = S.canvas.getBoundingClientRect();
  return [(e.clientX - r.left) * S.W / r.width, (e.clientY - r.top) * S.H / r.height];
}

function finish(S) {
  if (S.cur.length < 3) {
    S.info.textContent = "Χρειάζονται τουλάχιστον 3 σημεία (έχεις " + S.cur.length + ").";
    return;
  }
  S.spots.push({ points_perc: S.cur.map(function (p) { return [p[0] / S.W, p[1] / S.H]; }) });
  S.cur = [];
  sendValue(S);
  draw(S);
}

function undo(S) {
  if (S.cur.length) S.cur.pop();
  else if (S.spots.length) { S.spots.pop(); sendValue(S); }
  draw(S);
}

function clearAll(S) { S.cur = []; S.spots = []; sendValue(S); draw(S); }

function bind(S, root) {
  const canvas = S.canvas;
  canvas.addEventListener("mousemove", function (e) { S.mouse = pos(S, e); draw(S); });
  canvas.addEventListener("mouseleave", function () { S.mouse = null; draw(S); });
  canvas.addEventListener("click", function (e) { S.cur.push(pos(S, e)); canvas.focus(); draw(S); });
  canvas.addEventListener("dblclick", function () {
    S.cur.pop();            // το 2ο κλικ του διπλού κλικ είναι διπλότυπο
    finish(S);
  });
  canvas.addEventListener("contextmenu", function (e) { e.preventDefault(); finish(S); });
  // Τα πλήκτρα ακούγονται ΜΟΝΟ όταν ο καμβάς έχει focus (δεν επηρεάζουν την υπόλοιπη σελίδα).
  canvas.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); finish(S); }
    else if (e.key === "Backspace" || (e.ctrlKey && e.key.toLowerCase() === "z")) { e.preventDefault(); undo(S); }
    else if (e.key === "Escape") { S.cur = []; draw(S); }
  });
  root.querySelector("#finish").addEventListener("click", function () { finish(S); });
  root.querySelector("#undo").addEventListener("click", function () { undo(S); });
  root.querySelector("#clear").addEventListener("click", function () { clearAll(S); });
}

export default function (component) {
  const data = component.data || {};
  const root = component.parentElement;

  // Η κατάσταση κρατιέται πάνω στο στοιχείο· ασφαλές αν η συνάρτηση ξανατρέξει με νέα data.
  let S = root.__spotState;
  if (!S) {
    const canvas = root.querySelector("#c");
    S = root.__spotState = {
      canvas: canvas,
      ctx: canvas.getContext("2d"),
      info: root.querySelector("#info"),
      spots: Array.isArray(data.initial_spots) ? data.initial_spots.slice() : [],
      cur: [], mouse: null, img: null, imgSrc: null, W: 960, H: 540,
    };
    bind(S, root);
  }
  S.setStateValue = component.setStateValue;

  if (data.width && data.height) { S.W = data.width; S.H = data.height; }
  S.canvas.width = S.W;
  S.canvas.height = S.H;

  if (data.image && data.image !== S.imgSrc) {
    S.imgSrc = data.image;
    const img = new Image();
    img.onload = function () { S.img = img; draw(S); };
    img.src = data.image;
  } else {
    draw(S);
  }
}
"""

_component = st.components.v2.component("spot_drawer", html=_HTML, css=_CSS, js=_JS)


def spot_drawer(image, width, height, initial_spots, key):
    """Εμφανίζει τον καμβά και επιστρέφει τη λίστα θέσεων (ή None αν δεν έχει γίνει αλλαγή)."""
    result = _component(
        data={"image": image, "width": width, "height": height, "initial_spots": initial_spots},
        key=key,
        on_spots_change=lambda: None,
    )
    return result.spots
