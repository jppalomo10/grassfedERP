import pandas as pd
import streamlit as st
from db import run_query

clientes = pd.read_excel("Data.xlsx", sheet_name="Clientes")

if st.button("Cargar Clientes"):
    for index, row in clientes.iterrows():
        run_query("""INSERT INTO "Clientes" ("Nombre", "Teléfono", "Dirección", "Correo") VALUES (%s, %s, %s, %s)""", (row["Nombre"], row["Teléfono"], row["Dirección"], row["Correo"]), fetch="none")
    st.success("Clientes cargados correctamente")

st.write(run_query("SELECT table_schema, table_name FROM information_schema.tables WHERE table_name ILIKE 'clientes';", fetch="all"))