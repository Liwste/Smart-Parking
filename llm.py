"""
Smart Parking Management System - Cloud LLM Node
Διπλωματική Εργασία
Αυτό το script ακούει τα δεδομένα από το MQTT και χρησιμοποιεί το Google Gemini
ως "Έξυπνο Βοηθό" για να απαντάει σε ερωτήσεις του χρήστη σε φυσική γλώσσα.
"""
    #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
import paho.mqtt.client as mqtt
import json
import streamlit as st
import time
import sys
from groq import Groq

# ==========================================
# 1. ΡΥΘΜΙΣΕΙΣ GROQ API (Llama 3)
# ==========================================
GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
client = Groq(api_key=GROQ_API_KEY)

# ==========================================
# 2. ΡΥΘΜΙΣΕΙΣ MQTT & ΚΑΤΑΣΤΑΣΗ ΠΑΡΚΙΝΓΚ
# ==========================================
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "parking/diplomatiki/status"

current_parking_data = {}
last_update_time = None

def on_connect(mqtt_client, userdata, flags, rc):
    print(f"✅ Συνδέθηκε στον MQTT Broker (Κωδικός: {rc})")
    mqtt_client.subscribe(MQTT_TOPIC)
    print(f"📡 Ακούει για δεδομένα στο topic: {MQTT_TOPIC}...\n")

def on_message(mqtt_client, userdata, msg):
    global current_parking_data, last_update_time
    try:
        payload = msg.payload.decode('utf-8')
        current_parking_data = json.loads(payload)
        last_update_time = time.strftime("%H:%M:%S")
    except Exception as e:
        print(f"Σφάλμα ανάγνωσης μηνύματος: {e}")

mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect(MQTT_BROKER, MQTT_PORT)
mqtt_client.loop_start()

# ==========================================
# 3. Η ΛΟΓΙΚΗ ΤΟΥ LLM (Llama 3 μέσω Groq)
# ==========================================
def ask_parking_assistant(user_query):
    if not current_parking_data:
        return "Λυπάμαι, δεν έχω λάβει ακόμα δεδομένα από την κάμερα του πάρκινγκ."

    system_prompt = f"""
    Είσαι ένας ευγενικός βοηθός για ένα έξυπνο πάρκινγκ στην Ελλάδα.
    Αυτή τη στιγμή, η ώρα είναι {last_update_time} και η κατάσταση των θέσεων είναι:
    {json.dumps(current_parking_data, indent=2, ensure_ascii=False)}
    Απάντα πάντα στα Ελληνικά, σύντομα και φιλικά.
    """

    try:
        print("🤖 Το AI σκέφτεται... ")
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query}
            ],
            model="llama-3.1-8b-instant", # Το νέο, αναβαθμισμένο μοντέλοpy
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        return f"Σφάλμα επικοινωνίας με το API: {e}"

# ==========================================
# 4. ΔΙΕΠΑΦΗ ΧΡΗΣΤΗ (Τερματικό)
# ==========================================
time.sleep(2)
print("-" * 50)
print("Καλωσήρθατε στο Smart Parking LLM Interface!")
print("Γράψτε 'exit' για έξοδο.")
print("-" * 50)

while True:
    try:
        user_input = input("\n👤 Εσύ: ")
        if user_input.lower() in ['exit', 'quit', 'έξοδος']:
            break
        if user_input.strip() == "": continue

        answer = ask_parking_assistant(user_input)
        print(f"\n🅿️ Βοηθός Πάρκινγκ:\n{answer}")
        
    except KeyboardInterrupt:
        break

mqtt_client.loop_stop()
sys.exit(0)