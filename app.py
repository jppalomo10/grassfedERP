import streamlit as st
from auth import check_login

if not check_login():
    st.stop()


st.set_page_config(page_title="Menú Principal", page_icon="🔐", layout="centered")
st.title("Sistema ERP")

col1, col2 = st.columns(2)

col1.write(f"Bienvenido **{st.session_state.user}**")

if col2.button("Logout", type="secondary", use_container_width=True):
    st.session_state.authenticated = False
    st.session_state.user = None
    st.rerun()
