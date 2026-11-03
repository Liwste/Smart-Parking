import streamlit as st
import json
import html
from groq import Groq

# ==========================================
# 1. ΡΥΘΜΙΣΕΙΣ ΣΕΛΙΔΑΣ
# ==========================================
st.set_page_config(
    page_title="Smart Parking",
    page_icon="🅿️",
    layout="wide"
)

st.title("🅿️ Smart Parking Management System")

GROQ_API_KEY = st.secrets["GROQ_API_KEY"]

from mqtt_shared import get_mqtt_buffer, init_mqtt

mqtt_buffer = get_mqtt_buffer()
mqtt_client = init_mqtt()

if "parking_data" not in st.session_state:
    st.session_state.parking_data = {}
if "last_update" not in st.session_state:
    st.session_state.last_update = "No data has been received yet."

if mqtt_buffer["data"]:
    st.session_state.parking_data = mqtt_buffer["data"]
    st.session_state.last_update = mqtt_buffer["time"]

# ==========================================
# 2. SESSION STATE ΓΙΑ ΤΟ CHAT
# ==========================================
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hello! I am the parking digital assistant. How can I help you?"}
    ]

# ==========================================
# 3. ΔΙΑΤΑΞΗ ΟΘΟΝΗΣ (2 ΣΤΗΛΕΣ)
# ==========================================
col_parking, col_chat = st.columns([1, 1], gap="large")

# ------------------------------------------
# ΣΤΗΛΗ 1: ΟΠΤΙΚΗ ΚΑΤΑΣΤΑΣΗ ΠΑΡΚΙΝΓΚ (LIVE)
# ------------------------------------------
with col_parking:
    st.subheader("Parking Space Status")

    @st.fragment(run_every="2s")
    def display_parking_status():
        if globals()['mqtt_buffer']["data"]:
            if mqtt_buffer["data"]:
                st.session_state.parking_data = mqtt_buffer["data"]
                st.session_state.last_update = mqtt_buffer["time"]

        data = st.session_state.parking_data
        update_time = st.session_state.last_update

        st.write(f"**Last Update Time:** `{update_time}`")
        
        if mqtt_buffer.get("pi_online") is False:
            st.error("🔴 The camera node (Raspberry Pi) is offline. The spots below are the last known state and may be outdated.")
        
        if not data:
            st.warning("⏳ Waiting for data")
        else:
            total_spots = len(data)
            free_spots = sum(1 for status in data.values() if status == "Free")
            taken_spots = total_spots - free_spots

            # Καθαροί μετρητές χωρίς βέλη/deltas
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Spots", total_spots)
            m2.metric("Free", free_spots)
            m3.metric("Taken", taken_spots)

            st.divider()

            # Συμπαγείς κάρτες για τις θέσεις
            grid_cols = st.columns(3)
            for idx, (spot_id, status) in enumerate(data.items()):
                col_idx = idx % 3
                with grid_cols[col_idx]:
                    if status == "Free":
                        st.markdown(
                            f"""
                            <div style="background-color: rgba(40, 167, 69, 0.12); border: 1px solid #28a745; border-radius: 8px; padding: 8px; text-align: center; margin-bottom: 8px;">
                                <div style="font-weight: bold; font-size: 15px; color: #28a745;">{html.escape(spot_id.upper())}</div>
                                <div style="font-size: 13px; margin-top: 2px;">🟢 FREE</div>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                    else:
                        st.markdown(
                            f"""
                            <div style="background-color: rgba(220, 53, 69, 0.12); border: 1px solid #dc3545; border-radius: 8px; padding: 8px; text-align: center; margin-bottom: 8px;">
                                <div style="font-weight: bold; font-size: 15px; color: #dc3545;">{html.escape(spot_id.upper())}</div>
                                <div style="font-size: 13px; margin-top: 2px;">🔴 TAKEN</div>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )

    display_parking_status()

# ------------------------------------------
# ΣΤΗΛΗ 2: CHATBOT INTERFACE (LLM)
# ------------------------------------------
with col_chat:
    st.subheader("Ai Assistant")

    # Το πεδίο γραφής μένει πάντα στην κορυφή· τα νεότερα μηνύματα εμφανίζονται από κάτω του, πρώτα.
    user_input = st.chat_input("Ask me anything about parking...")

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})

        current_data = st.session_state.parking_data
        current_time = st.session_state.last_update

        if not current_data:
            bot_reply = "⚠️ I'm sorry, I haven't received live data from the camera yet. Make sure `main_pi.py` is running!"
        else:
            with st.spinner("Thinking..."):
                offline_note = ""
                if mqtt_buffer.get("pi_online") is False:
                    offline_note = "WARNING: the camera is OFFLINE, so this is only the last known state and may be outdated. Tell the user so.\n"
                system_prompt = f"""
                The last update from the camera was at {current_time} and the status of the spots is:
                {json.dumps(current_data, indent=2, ensure_ascii=False)}
                {offline_note}
                Rules:
                1. Always answer in English or Greek depending on the question language, briefly and in a friendly manner.
                2. Rely EXCLUSIVELY on the JSON data above to state which spot is free or occupied.
                """

                try:
                    client = Groq(api_key=GROQ_API_KEY)

                    api_messages = [{"role": "system", "content": system_prompt}]
                    for msg in st.session_state.messages[-10:]:
                        api_messages.append({"role": msg["role"], "content": msg["content"]})

                    response = client.chat.completions.create(
                        model="openai/gpt-oss-20b",
                        messages=api_messages
                    )
                    bot_reply = response.choices[0].message.content
                except Exception as e:
                    print(f"Groq error: {e}")
                    bot_reply = "Σφάλμα επικοινωνίας. Δοκίμασε ξανά σε λίγο."

        st.session_state.messages.append({"role": "assistant", "content": bot_reply})

    # Ομαδοποίηση σε ζεύγη (ερώτηση + απάντηση) και εμφάνιση με το νεότερο ζεύγος πρώτο.
    turns = []
    for message in st.session_state.messages:
        if message["role"] == "user" or not turns:
            turns.append([message])
        else:
            turns[-1].append(message)

    for turn in reversed(turns):
        for message in turn:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
