"""
Custom Streamlit component: καμβάς για σχεδίαση θέσεων στάθμευσης (polygons).
Κάνεις κλικ στις γωνίες κάθε θέσης· μικρά σημεία, διακεκομμένη γραμμή που
ακολουθεί το ποντίκι, ολοκλήρωση με Enter / διπλό κλικ / δεξί κλικ.
Επιστρέφει λίστα [{"points_perc": [[x, y], ...]}, ...].
"""
from pathlib import Path

import streamlit.components.v1 as components

# Το frontend (HTML/JS του καμβά) είναι αρχείο μέσα στο repo και όχι προσωρινό αρχείο,
# ώστε να είναι πάντα διαθέσιμο στο Streamlit Cloud.
_FRONTEND_DIR = Path(__file__).resolve().parent / "spot_drawer_frontend"

spot_drawer = components.declare_component("spot_drawer", path=str(_FRONTEND_DIR))
