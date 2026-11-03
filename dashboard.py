import streamlit as st

pg = st.navigation([
    st.Page("dashboard_page.py", title="Dashboard", icon="🅿️", default=True),
    st.Page("pages/2_Spot_Setup.py", title="Spot Setup", icon="🗺️"),
])
pg.run()
