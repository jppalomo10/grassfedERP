# Importaciones
import streamlit as st
import pandas as pd
from db import run_query
from auth import check_login

# Configuración de la página
if not check_login():
    st.stop()

if st.sidebar.button("Cerrar Sesión"):
    st.session_state.authenticated = False
    st.rerun()

st.set_page_config(
    page_title="Sistema ERP",
    page_icon=":data:",
    layout="wide"
)

col1, col2 = st.columns(2)

with col1:
    st.title("🏠 Menú principal")
    st.markdown("""
    Bienvenido a la aplicación.
    Selecciona una sección desde el menú lateral.
    """)

with col2:
    st.subheader("Estado de la base de datos")
    row = run_query("select now() as ahora;", fetch="one")
    st.write("Conexión exitosa ✅", row["ahora"])
