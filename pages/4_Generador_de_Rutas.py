import streamlit as st
import pandas as pd
from db import run_query
from auth import check_login, role_badge
from pdf_utils import generar_rutas_envio_pdf

# ── Configuración de página ──────────────────────────────────────────
st.set_page_config(
    page_title="Generador de Rutas",
    page_icon="🚚",
    layout="wide",
)

# ── Autenticación ────────────────────────────────────────────────────
if not check_login():
    st.stop()

st.sidebar.markdown(f"**{st.session_state.user}** · {role_badge()}")
if st.sidebar.button("Cerrar Sesión", key="logout_rutas"):
    for key in ["authenticated", "user", "role"]:
        st.session_state.pop(key, None)
    st.rerun()


# ══════════════════════════════════════════════════════════════════════
# HELPERS DE DATOS
# ══════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=120)
def get_pedidos_pendientes_envio():
    """Pedidos pendientes de envío con peso total y datos del cliente."""
    rows = run_query("""
        SELECT p."ID_Pedido",
               c."Nombre"    AS "Cliente",
               c."Teléfono",
               c."Dirección",
               COALESCE(SUM(d."Peso"), 0) AS "Peso_Total",
               p."Envío"
        FROM "Pedidos" p
        JOIN "Clientes" c      ON p."Cliente"    = c."Teléfono"
        LEFT JOIN "DetallePedido" d ON d."ID_Pedido" = p."ID_Pedido"
        WHERE p."Entregado" = false
          AND p."Estado" != 'Anulado'
        GROUP BY p."ID_Pedido", c."Nombre", c."Teléfono", c."Dirección", p."Envío"
        ORDER BY p."Envío", c."Nombre"
    """)
    return rows if rows else []


# ══════════════════════════════════════════════════════════════════════
# INICIALIZAR SESSION STATE
# ══════════════════════════════════════════════════════════════════════

if "rutas" not in st.session_state:
    st.session_state.rutas = {}  # { nombre_ruta: [id_pedido, ...] }

if "num_rutas" not in st.session_state:
    st.session_state.num_rutas = 1


# ══════════════════════════════════════════════════════════════════════
# PÁGINA PRINCIPAL
# ══════════════════════════════════════════════════════════════════════

st.title("🚚 Generador de Rutas")
st.markdown("Selecciona los pedidos pendientes y asígnalos a rutas distintas para cada motorista.")
st.divider()

# Obtener pedidos pendientes
pedidos_raw = get_pedidos_pendientes_envio()

if not pedidos_raw:
    st.info("✅ No hay pedidos pendientes de envío.")
    st.stop()

# Convertir a DataFrame para mostrar
df_pedidos = pd.DataFrame(pedidos_raw)
df_pedidos["Peso_Total"] = df_pedidos["Peso_Total"].astype(float)

st.subheader(f"📦 Pedidos pendientes de envío ({len(df_pedidos)})")

st.dataframe(
    df_pedidos,
    use_container_width=True,
    hide_index=True,
    column_config={
        "ID_Pedido": st.column_config.NumberColumn("# Factura"),
        "Peso_Total": st.column_config.NumberColumn("Peso (lb)", format="%.2f"),
        "Envío": st.column_config.TextColumn("Zona de Envío"),
    },
)

st.divider()

# ══════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN DE RUTAS
# ══════════════════════════════════════════════════════════════════════

st.subheader("🗺️ Configurar Rutas")

# Controles para número de rutas
col_config1, col_config2 = st.columns([1, 3])
with col_config1:
    num_rutas = st.number_input(
        "Número de rutas",
        min_value=1,
        max_value=10,
        value=st.session_state.num_rutas,
        step=1,
        key="input_num_rutas",
    )
    st.session_state.num_rutas = num_rutas

with col_config2:
    st.info(
        "💡 Asigna un nombre a cada ruta (ej. nombre del motorista) y "
        "selecciona los pedidos que corresponden a cada una."
    )

st.divider()

# ══════════════════════════════════════════════════════════════════════
# ASIGNACIÓN DE PEDIDOS POR RUTA
# ══════════════════════════════════════════════════════════════════════

# Índice de IDs de pedidos disponibles
todos_los_ids = [p["ID_Pedido"] for p in pedidos_raw]

# Diccionario rápido para buscar datos de pedido por ID
pedido_por_id = {p["ID_Pedido"]: p for p in pedidos_raw}

# Recopilar las asignaciones
rutas_config = {}  # { nombre: [ids seleccionados] }

for i in range(int(num_rutas)):
    ruta_key = f"ruta_{i}"

    with st.container(border=True):
        col_name, col_count = st.columns([2, 1])

        with col_name:
            nombre_ruta = st.text_input(
                f"🏷️ Nombre de la Ruta {i + 1}",
                value=f"Ruta {i + 1}",
                key=f"nombre_{ruta_key}",
                placeholder="Ej: Juan Pérez, Ruta Norte...",
            )

        # Crear opciones con info legible para el multiselect
        opciones_display = []
        opciones_map = {}  # display_str → id
        for pid in todos_los_ids:
            p = pedido_por_id[pid]
            label = f"#{pid} – {p['Cliente']} ({p['Envío']}) – {float(p['Peso_Total']):.1f} lb"
            opciones_display.append(label)
            opciones_map[label] = pid

        seleccionados_display = st.multiselect(
            f"📋 Pedidos para **{nombre_ruta}**",
            options=opciones_display,
            key=f"pedidos_{ruta_key}",
            placeholder="Selecciona pedidos para esta ruta...",
        )

        # Convertir display labels a IDs
        ids_seleccionados = [opciones_map[s] for s in seleccionados_display]
        rutas_config[nombre_ruta] = ids_seleccionados

        # Mostrar resumen de la ruta
        with col_count:
            n_pedidos = len(ids_seleccionados)
            if n_pedidos > 0:
                peso_ruta = sum(
                    float(pedido_por_id[pid]["Peso_Total"])
                    for pid in ids_seleccionados
                )
                st.metric("Pedidos", n_pedidos)
                st.metric("Peso total", f"{peso_ruta:.1f} lb")
            else:
                st.metric("Pedidos", 0)
                st.metric("Peso total", "0 lb")


# ══════════════════════════════════════════════════════════════════════
# VALIDACIÓN Y GENERACIÓN
# ══════════════════════════════════════════════════════════════════════

st.divider()

# Detectar pedidos duplicados entre rutas
todos_asignados = []
for nombre, ids in rutas_config.items():
    todos_asignados.extend(ids)

duplicados = set(x for x in todos_asignados if todos_asignados.count(x) > 1)
sin_asignar = set(todos_los_ids) - set(todos_asignados)

# Mostrar advertencias
col_warn1, col_warn2 = st.columns(2)

with col_warn1:
    if duplicados:
        pedidos_dup_str = ", ".join(f"#{d}" for d in duplicados)
        st.warning(f"⚠️ Pedidos duplicados en varias rutas: {pedidos_dup_str}")
    elif todos_asignados:
        st.success("✅ No hay pedidos duplicados entre rutas.")

with col_warn2:
    if sin_asignar:
        pedidos_sin_str = ", ".join(f"#{s}" for s in sorted(sin_asignar))
        st.warning(f"📋 Pedidos sin asignar: {pedidos_sin_str}")
    elif todos_asignados:
        st.success("✅ Todos los pedidos están asignados.")

st.divider()

# ══════════════════════════════════════════════════════════════════════
# GENERAR PDFs
# ══════════════════════════════════════════════════════════════════════

st.subheader("📄 Generar Hojas de Ruta")

# Filtrar rutas vacías
rutas_con_pedidos = {
    nombre: ids for nombre, ids in rutas_config.items() if ids
}

if not rutas_con_pedidos:
    st.info("Asigna pedidos a al menos una ruta para generar las hojas de ruta.")
    st.stop()

# Generar un PDF individual por ruta
cols_rutas = st.columns(min(len(rutas_con_pedidos), 3))

for idx, (nombre, ids) in enumerate(rutas_con_pedidos.items()):
    col = cols_rutas[idx % len(cols_rutas)]

    pedidos_ruta = [pedido_por_id[pid] for pid in ids if pid in pedido_por_id]
    peso_total_ruta = sum(float(p["Peso_Total"]) for p in pedidos_ruta)

    with col:
        with st.container(border=True):
            st.markdown(f"### 🚛 {nombre}")
            st.markdown(f"**{len(pedidos_ruta)}** pedidos · **{peso_total_ruta:.1f} lb**")

            # Mostrar tabla resumida
            df_ruta = pd.DataFrame(pedidos_ruta)
            if not df_ruta.empty:
                df_ruta["Peso_Total"] = df_ruta["Peso_Total"].astype(float)
                st.dataframe(
                    df_ruta[["ID_Pedido", "Cliente", "Envío", "Peso_Total"]],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "ID_Pedido": st.column_config.NumberColumn("# Factura"),
                        "Peso_Total": st.column_config.NumberColumn("Peso (lb)", format="%.2f"),
                    },
                )

            # Botón de descarga individual
            pdf_bytes = generar_rutas_envio_pdf(pedidos_ruta, nombre_ruta=nombre)
            nombre_archivo = nombre.replace(" ", "_")
            st.download_button(
                label=f"📥 Descargar Ruta",
                data=pdf_bytes,
                file_name=f"Ruta_{nombre_archivo}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True,
                key=f"download_ruta_{idx}",
            )

# ── Botón para descargar todas las rutas como ZIP ────────────────────
st.divider()

if len(rutas_con_pedidos) > 1:
    if st.button("📦 Descargar Todas las Rutas (ZIP)", type="primary", use_container_width=True):
        import zipfile
        from io import BytesIO

        zip_buf = BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for nombre, ids in rutas_con_pedidos.items():
                pedidos_ruta = [pedido_por_id[pid] for pid in ids if pid in pedido_por_id]
                pdf_bytes = generar_rutas_envio_pdf(pedidos_ruta, nombre_ruta=nombre)
                nombre_archivo = nombre.replace(" ", "_")
                zf.writestr(f"Ruta_{nombre_archivo}.pdf", pdf_bytes.read())

        zip_buf.seek(0)
        st.download_button(
            label="⬇️ Descargar ZIP",
            data=zip_buf,
            file_name="Rutas_Envio.zip",
            mime="application/zip",
            use_container_width=True,
        )
