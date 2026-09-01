# 🅿️ Smart Parking Management System

A Smart Parking Management System that uses computer vision, YOLO object detection, MQTT communication, Streamlit, and an AI chatbot to monitor parking space availability in real time.

## 📌 Project Description

The system processes a parking video using YOLO and OpenCV in order to detect whether parking spaces are free or occupied.

The detected parking status is sent through MQTT to an online Streamlit dashboard.

The dashboard displays the current parking status and also includes an AI-powered chatbot that can answer questions about the available parking spaces.

## ⚙️ System Architecture

The system follows the architecture:

Video / Camera  
↓  
YOLO + OpenCV  
↓  
Python (`main.py`)  
↓  
MQTT Publisher  
↓  
HiveMQ Broker  
↓  
MQTT Subscriber  
↓  
Streamlit Dashboard  
↓  
AI Chatbot

## 🚗 Main Features

- Real-time parking space monitoring
- Vehicle detection using YOLO
- Free / occupied parking space classification
- MQTT communication
- Retained MQTT messages for keeping the latest parking status
- Online Streamlit dashboard
- Live parking statistics
- AI chatbot for parking-related questions
- Greek and English chatbot support

## 🧠 Technologies Used

- Python
- YOLO
- Ultralytics
- OpenCV
- MQTT
- Paho MQTT
- HiveMQ
- Streamlit
- Groq API
- GPT-OSS

## 📂 Project Structure

```text
Smart-Parking/
│
├── main.py
│   └── Runs the YOLO parking detection and publishes data through MQTT
│
├── dashboard.py
│   └── Streamlit dashboard, MQTT subscriber and AI chatbot
│
├── llm.py
│   └── Additional LLM functionality
│
├── requirements.txt
│   └── Required Python packages
│
├── .gitignore
│   └── Prevents sensitive and unnecessary files from being uploaded
│
└── .streamlit/
    └── secrets.toml
        └── Stores API keys locally (not uploaded to GitHub)

📡 MQTT Communication

The system uses the public HiveMQ MQTT broker.

Broker: broker.hivemq.com
Port: 1883
Topic: parking/diplomatiki/status/stel

The parking detection system publishes JSON messages containing the current status of every parking space.

Example:

{
    "spot1": "Free",
    "spot2": "Taken",
    "spot3": "Free"
}

MQTT retained messages are enabled so that the Streamlit dashboard can retrieve the latest known parking status even after reconnecting or refreshing.

▶️ Running the Detection System

Install the required dependencies:

pip install -r requirements.txt

Run the parking detection system:

python main.py

The YOLO detection system will process the parking video and publish the parking status to the MQTT broker.

🌐 Running the Dashboard Locally

Run:

streamlit run dashboard.py

The dashboard will normally open at:

http://localhost:8501
☁️ Streamlit Cloud

The dashboard is also deployed using Streamlit Community Cloud.

The online Streamlit application receives parking information directly from the MQTT broker, meaning that the dashboard can remain online independently of the computer running the YOLO detection system.

When main.py starts publishing parking data, the online dashboard automatically receives and displays the updated status.

🤖 AI Chatbot

The dashboard contains an AI-powered assistant using the Groq API.

The chatbot receives the current parking status and can answer questions such as:

Which parking spaces are free?
How many parking spaces are available?
Is spot 3 occupied?
Ποιες θέσεις είναι ελεύθερες;
Πόσες διαθέσιμες θέσεις υπάρχουν;

The chatbot is instructed to use the live MQTT parking data when answering questions about parking availability.

🔐 API Key Security

API keys are not stored directly inside the Python source code.

Locally, the Groq API key is stored in:

.streamlit/secrets.toml

Example:

GROQ_API_KEY = "YOUR_API_KEY"

The file is excluded from GitHub through .gitignore.

.streamlit/secrets.toml
.env
__pycache__/

For Streamlit Community Cloud, the API key is stored using Streamlit's built-in Secrets configuration.

🎓 Purpose

This project was developed as a Smart Parking Management System demonstrating the integration of:

Artificial Intelligence
Computer Vision
IoT communication
Cloud-based dashboards
Large Language Models

The goal is to create an intelligent system capable of monitoring parking availability and providing users with real-time information through an accessible web interface.
