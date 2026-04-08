import streamlit as st
import pandas as pd
from db import run_query
from auth import check_login, role_badge, require_role

# ── Configuración de página ──────────────────────────────────────────
st.set_page_config(
    page_title="Consola SQL",
    page_icon="💻",
    layout="wide",
)

# ── Autenticación ────────────────────────────────────────────────────
if not check_login():
    st.stop()

# Requerir rol "dev" estricto
require_role(["dev"])

st.sidebar.markdown(f"**{st.session_state.user}** · {role_badge()}")
if st.sidebar.button("Cerrar Sesión"):
    for key in ["authenticated", "user", "role"]:
        st.session_state.pop(key, None)
    st.rerun()

# ── Interfaz ─────────────────────────────────────────────────────────
st.title("💻 Consola de Base de Datos")
st.markdown("Ejecuta consultas SQL directamente contra la base de datos de producción.")
st.warning("⚠️ **Advertencia:** Esta herramienta tiene acceso directo a producción. Úsala con precaución.")

query = st.text_area("✍️ Ingrese su consulta SQL:", height=200, placeholder="SELECT * FROM \"Clientes\" LIMIT 10;")

if st.button("▶️ Ejecutar Consulta", type="primary"):
    if query.strip():
        try:
            query_upper = query.strip().upper()
            
            with st.spinner("Ejecutando..."):
                # Para SELECT, WITH, o sentencias con RETURNING mostramos los resultados
                if query_upper.startswith("SELECT") or query_upper.startswith("WITH") or "RETURNING" in query_upper:
                    rows = run_query(query)
                    
                    if rows:
                        df = pd.DataFrame(rows)
                        st.success(f"✅ Consulta ejecutada con éxito. Filas devueltas: {len(df)}")
                        st.dataframe(df, use_container_width=True)
                    else:
                        st.info("La consulta se ejecutó con éxito pero no devolvió resultados.")
                else:
                    # Para INSERT, UPDATE, DELETE (sin RETURNING), CREATE, DROP, etc.
                    run_query(query, fetch="none")
                    st.success("✅ Instrucción ejecutada con éxito.")
                    
        except Exception as e:
            st.error(f"❌ Error al ejecutar la consulta: {str(e)}")
    else:
        st.error("⚠️ Por favor ingrese una consulta antes de ejecutar.")
