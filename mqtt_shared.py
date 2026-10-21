import streamlit as st
import paho.mqtt.client as mqtt
import json
import time
import random

MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883

MQTT_TOPIC_STATUS = "parking/diplomatiki/status/stel"
MQTT_TOPIC_SNAPSHOT_REQUEST = "parking/diplomatiki/snapshot/request/stel"
MQTT_TOPIC_SNAPSHOT_RESPONSE = "parking/diplomatiki/snapshot/response/stel"
MQTT_TOPIC_CONFIG = "parking/diplomatiki/config/stel"


@st.cache_resource
def get_mqtt_buffer():
    return {
        "data": {},
        "time": "No data has been received yet.",
        "snapshot_b64": None,
        "snapshot_time": None,
    }


@st.cache_resource
def init_mqtt():
    buffer = get_mqtt_buffer()
    client_id = f"streamlit_dashboard_{random.randint(1000, 9999)}"

    def on_connect(client, userdata, flags, rc, *args):
        print("✅ Dashboard connected to MQTT!")
        client.subscribe(MQTT_TOPIC_STATUS, qos=1)
        client.subscribe(MQTT_TOPIC_SNAPSHOT_RESPONSE, qos=1)

    def on_message(client, userdata, msg):
        try:
            if msg.topic == MQTT_TOPIC_STATUS:
                parsed = json.loads(msg.payload.decode('utf-8'))
                buffer["data"] = parsed
                buffer["time"] = time.strftime("%H:%M:%S")
                print(f"📩 MQTT Status: {parsed}")

            elif msg.topic == MQTT_TOPIC_SNAPSHOT_RESPONSE:
                buffer["snapshot_b64"] = msg.payload.decode('utf-8')
                buffer["snapshot_time"] = time.strftime("%H:%M:%S")
                print("📸 MQTT Snapshot received")

        except Exception as e:
            print(f"MQTT Error: {e}")

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
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