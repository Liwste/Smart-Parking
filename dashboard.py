import streamlit as st
import paho.mqtt.client as mqtt
import json
import time
import random
import os
from groq import Groq

# ==========================================
# 1. ΡΥΘΜΙΣΕΙΣ ΣΕΛΙΔΑΣ
# ==========================================
st.set_page_config(
    page_title="Smart Parking Dashboard",
    page_icon="🅿️",
    layout="wide"
)

st.title("🅿️ Smart Parking Management System")

GROQ_API_KEY = "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"

# ==========================================
# 2. THREAD-SAFE GLOBAL CONTAINER & SESSION STATE
# ==========================================
if 'mqtt_buffer' not in globals():
    globals()['mqtt_buffer'] = {
        "data": {},
        "time": "No data has been received yet."
    }

if "parking_data" not in st.session_state:
    st.session_state.parking_data = {}

if "last_update" not in st.session_state:
    st.session_state.last_update = "No data has been received yet."

# ==========================================
# 3. MQTT CLIENT SETUP
# ==========================================
MQTT_BROKER = "broker.emqx.io"  # ή broker.hivemq.com
MQTT_PORT = 1883
MQTT_TOPIC = "parking/diplomatiki/status"

@st.cache_resource
def init_mqtt():
    client_id = f"streamlit_dashboard_{random.randint(1000, 9999)}"

    def on_connect(client, userdata, flags, rc, *args):
        print("✅ Dashboard connected to MQTT!")
        client.subscribe(MQTT_TOPIC)

    def on_message(client, userdata, msg):
        try:
            payload = msg.payload.decode('utf-8')
            parsed = json.loads(payload)
            globals()['mqtt_buffer']["data"] = parsed
            globals()['mqtt_buffer']["time"] = time.strftime("%H:%M:%S")
            print(f"📩 MQTT Received: {parsed}")
        except Exception as e:
            print(f"MQTT Error: {e}")

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=client_id)
    except AttributeError:
        client = mqtt.Client(client_id=client_id)

    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        client.loop_start()
    except Exception as e:
        print(f"Connection Error: {e}")
        
    return client

mqtt_client = init_mqtt()

# Συγχρονισμός του session_state
if globals()['mqtt_buffer']["data"]:
    st.session_state.parking_data = globals()['mqtt_buffer']["data"]
    st.session_state.last_update = globals()['mqtt_buffer']["time"]

# ==========================================
# 4. SESSION STATE ΓΙΑ ΤΟ CHAT
# ==========================================
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hello! I am the parking digital assistant. How can I help you?"}
    ]

# ==========================================
# 5. ΔΙΑΤΑΞΗ ΟΘΟΝΗΣ (2 ΣΤΗΛΕΣ)
# ==========================================
col_parking, col_chat = st.columns([1, 1], gap="large")

# ------------------------------------------
# ΣΤΗΛΗ 1: ΟΠΤΙΚΗ ΚΑΤΑΣΤΑΣΗ ΠΑΡΚΙΝΓΚ (LIVE)
# ------------------------------------------
with col_parking:
    st.subheader("📊 Parking Space Status")

    @st.fragment(run_every="2s")
    def display_parking_status():
        if globals()['mqtt_buffer']["data"]:
            st.session_state.parking_data = globals()['mqtt_buffer']["data"]
            st.session_state.last_update = globals()['mqtt_buffer']["time"]

        data = st.session_state.parking_data
        update_time = st.session_state.last_update

        st.write(f"**Last Update Time:** `{update_time}`")
        
        if not data:
            st.warning("⏳ Waiting for data from `main.py`...")
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
                                <div style="font-weight: bold; font-size: 15px; color: #28a745;">{spot_id.upper()}</div>
                                <div style="font-size: 13px; margin-top: 2px;">🟢 FREE</div>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                    else:
                        st.markdown(
                            f"""
                            <div style="background-color: rgba(220, 53, 69, 0.12); border: 1px solid #dc3545; border-radius: 8px; padding: 8px; text-align: center; margin-bottom: 8px;">
                                <div style="font-weight: bold; font-size: 15px; color: #dc3545;">{spot_id.upper()}</div>
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
    st.subheader("🤖 Smart Parking Assistant")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if user_input := st.chat_input("Ask me anything about parking..."):
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            current_data = st.session_state.parking_data
            current_time = st.session_state.last_update

            if not current_data:
                bot_reply = "⚠️ I'm sorry, I haven't received live data from the camera yet. Make sure `main.py` is running!"
                st.warning(bot_reply)
            else:
                with st.spinner("Thinking..."):
                    system_prompt = f"""
                    Right now, the time is {current_time} and the status of the spots is:
                    {json.dumps(current_data, indent=2, ensure_ascii=False)}
                    
                    Rules:
                    1. Always answer in English or Greek depending on the question language(never answer in different language), briefly and in a friendly manner..
                    2. Rely EXCLUSIVELY on the JSON data above to state which spot is free or occupied..
                    """

                    try:
                        client = Groq(api_key=GROQ_API_KEY)
                        
                        api_messages = [{"role": "system", "content": system_prompt}]
                        for msg in st.session_state.messages:
                            api_messages.append({"role": msg["role"], "content": msg["content"]})

                        response = client.chat.completions.create(
                            model="llama-3.1-8b-instant",
                            messages=api_messages
                        )
                        bot_reply = response.choices[0].message.content
                    except Exception as e:
                        bot_reply = f"Σφάλμα επικοινωνίας: {e}"

                    st.markdown(bot_reply)

        st.session_state.messages.append({"role": "assistant", "content": bot_reply})
