import streamlit as st
import pandas as pd
import time
import uuid
from datetime import date
from db import run_query
from auth import check_login, role_badge

# ── Configuración de página ──────────────────────────────────────────
st.set_page_config(
    page_title="Registro de Movimientos",
    page_icon="📦",
    layout="wide",
)

# ── Autenticación ────────────────────────────────────────────────────
if not check_login():
    st.stop()

st.sidebar.markdown(f"**{st.session_state.user}** · {role_badge()}")
if st.sidebar.button("Cerrar Sesión"):
    for key in ["authenticated", "user", "role"]:
        st.session_state.pop(key, None)
    st.rerun()

# ── Helpers de datos ─────────────────────────────────────────────────
@st.cache_data(ttl=120)
def get_productos():
    """Devuelve DataFrame con todos los productos."""
    rows = run_query(
        'SELECT "SKU", "Producto" FROM "Productos" ORDER BY "Producto"'
    )
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["SKU", "Producto"])


def generar_id_movimiento():
    """Genera un ID de movimiento único (prefijo MOV- + 8 caracteres)."""
    return f"MOV-{uuid.uuid4().hex[:8].upper()}"


def insertar_movimiento(id_mov, sku, fecha, debe, haber):
    """Inserta un registro en MovimientosInventario."""
    run_query(
        """
        INSERT INTO "MovimientosInventario"
            ("ID_Movimiento", "SKU", "Fecha", "Debe", "Haber")
        VALUES (%s, %s, %s, %s, %s)
        """,
        params=(id_mov, sku, fecha, debe, haber),
        fetch="none",
    )


@st.cache_data(ttl=120)
def get_movimientos_recientes(limit=50):
    """Devuelve los últimos movimientos registrados."""
    rows = run_query(
        """
        SELECT m."ID_Movimiento", m."Fecha", p."Producto", m."SKU",
               m."Debe", m."Haber"
        FROM "MovimientosInventario" m
        JOIN "Productos" p ON p."SKU" = m."SKU"
        ORDER BY m."Fecha" DESC, m."ID_Movimiento"
        LIMIT %s
        """,
        params=(limit,),
    )
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["ID_Movimiento", "Fecha", "Producto", "SKU", "Debe", "Haber"]
    )


# ── Cargar catálogos ─────────────────────────────────────────────────
df_productos = get_productos()
productos_lista = df_productos["Producto"].tolist() if not df_productos.empty else []
sku_map = dict(zip(df_productos["Producto"], df_productos["SKU"])) if not df_productos.empty else {}

# ── Título ───────────────────────────────────────────────────────────
st.title("📦 Registro de Movimientos de Inventario")
st.divider()

# ══════════════════════════════════════════════════════════════════════
# TABS PRINCIPALES
# ══════════════════════════════════════════════════════════════════════
tab_ingreso, tab_transformacion, tab_historial = st.tabs(
    ["📥 Ingresos de Inventario", "🔄 Transformaciones", "📋 Historial"]
)

# ══════════════════════════════════════════════════════════════════════
# TAB 1 – INGRESOS DE INVENTARIO
# ══════════════════════════════════════════════════════════════════════
with tab_ingreso:
    st.subheader("Registrar ingreso de producto")
    st.caption("Registra productos que ingresan al inventario (compras, producción, devoluciones, etc.)")

    # Inicializar estado
    if "lineas_ingreso" not in st.session_state:
        st.session_state.lineas_ingreso = []

    col_fecha_ing = st.columns([1, 2])
    with col_fecha_ing[0]:
        fecha_ingreso = st.date_input("📅 Fecha del ingreso", value=date.today(), key="fecha_ing")

    with col_fecha_ing[1]:
        id_mov = st.text_input("Correlativo", key="correlativo_ingreso")

    st.markdown("---")

    # ── Agregar productos al ingreso ─────────────────────────────────
    with st.expander("➕ Agregar producto al ingreso", expanded=True):
        ci1, ci2 = st.columns([3, 1])
        with ci1:
            prod_ing = st.selectbox(
                "Producto",
                [""] + productos_lista,
                key="sel_prod_ing",
            )
        with ci2:
            peso_ing = st.number_input(
                "Peso (lb)", min_value=0.0, value=0.0,
                step=0.25, format="%.2f", key="peso_ing",
            )

        comentario_ing = st.text_input("Comentario (opcional)", key="com_ing",
                                        placeholder="Ej: Compra a proveedor X")

        if st.button("➕ Agregar línea de ingreso", type="primary", disabled=(not prod_ing or peso_ing <= 0)):
            st.session_state.lineas_ingreso.append({
                "Producto": prod_ing,
                "SKU": sku_map.get(prod_ing, ""),
                "Peso (lb)": peso_ing,
                "Comentario": comentario_ing,
            })
            st.rerun()

    # ── Tabla de líneas de ingreso ───────────────────────────────────
    if st.session_state.lineas_ingreso:
        st.markdown("#### 📋 Líneas del ingreso")
        df_ing = pd.DataFrame(st.session_state.lineas_ingreso)
        st.dataframe(
            df_ing[["Producto", "Peso (lb)", "Comentario"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Peso (lb)": st.column_config.NumberColumn("Peso (lb)", format="%.2f"),
            },
        )

        # Botones para quitar líneas
        cols_del_ing = st.columns(len(st.session_state.lineas_ingreso))
        for i, col in enumerate(cols_del_ing):
            with col:
                if st.button(f"🗑️ Quitar #{i+1}", key=f"del_ing_{i}"):
                    st.session_state.lineas_ingreso.pop(i)
                    st.rerun()

        total_peso_ing = sum(l["Peso (lb)"] for l in st.session_state.lineas_ingreso)
        st.markdown(f"**Peso total a ingresar:** {total_peso_ing:,.2f} lb")

        # ── Botones de acción ────────────────────────────────────────
        col_g, col_l = st.columns(2)
        with col_g:
            btn_guardar_ing = st.button(
                "✅ Guardar Ingreso", type="primary",
                use_container_width=True, key="btn_g_ing",
            )
        with col_l:
            if st.button("🧹 Limpiar", use_container_width=True, key="btn_l_ing"):
                st.session_state.lineas_ingreso = []
                st.rerun()

        if btn_guardar_ing:
            try:
                for linea in st.session_state.lineas_ingreso:
                    insertar_movimiento(
                        id_mov,
                        linea["SKU"],
                        fecha_ingreso,
                        linea["Peso (lb)"],  # Debe (ingresa)
                        None,                 # Haber vacío
                    )
                st.success(f"✅ Ingreso **{id_mov}** registrado exitosamente.")
                get_movimientos_recientes.clear()
                st.balloons()
                time.sleep(2)
                st.session_state.lineas_ingreso = []
                st.rerun()
            except Exception as e:
                st.error(f"Error al guardar: {e}")
    else:
        st.info("Aún no ha agregado productos al ingreso.")


# ══════════════════════════════════════════════════════════════════════
# TAB 2 – TRANSFORMACIONES (Partida de Diario)
# ══════════════════════════════════════════════════════════════════════
with tab_transformacion:
    st.subheader("Registrar transformación de productos")
    st.caption(
        "Funciona como una partida de diario contable: los productos consumidos "
        "van al **Haber** (salen) y los productos resultantes van al **Debe** (entran). "
        "El peso total del Debe y Haber deben estar balanceados."
    )

    col_fecha_tr = st.columns([1, 2])
    with col_fecha_tr[0]:
        fecha_transf = st.date_input("📅 Fecha de transformación", value=date.today(), key="fecha_tr")

    with col_fecha_tr[1]:
        id_mov = st.text_input("Correlativo", key="correlativo_transformacion")

    st.markdown("---")

    # ── Inicializar estado del data_editor ───────────────────────────
    if "df_transformacion" not in st.session_state:
        st.session_state.df_transformacion = pd.DataFrame(
            columns=["Producto", "Debe", "Haber"]
        )

    st.markdown("#### 📝 Partida de Transformación")
    st.markdown(
        "> **Debe** = Producto que **entra** al inventario (resultado)  \n"
        "> **Haber** = Producto que **sale** del inventario (materia prima consumida)"
    )

    # ── Data editor ──────────────────────────────────────────────────
    edited_df = st.data_editor(
        st.session_state.df_transformacion,
        num_rows="dynamic",
        use_container_width=True,
        key="editor_transf",
        column_config={
            "Producto": st.column_config.SelectboxColumn(
                "Producto",
                options=productos_lista,
                required=True,
                width="large",
            ),
            "Debe": st.column_config.NumberColumn(
                "Debe (lb)",
                help="Peso del producto que ENTRA al inventario",
                min_value=0.0,
                format="%.2f",
                default=None,
            ),
            "Haber": st.column_config.NumberColumn(
                "Haber (lb)",
                help="Peso del producto que SALE del inventario",
                min_value=0.0,
                format="%.2f",
                default=None,
            ),
        },
    )

    # ── Resumen de la partida ────────────────────────────────────────
    if not edited_df.empty and edited_df["Producto"].notna().any():
        # Limpiar filas vacías
        df_valido = edited_df.dropna(subset=["Producto"]).copy()

        if not df_valido.empty:
            total_debe = df_valido["Debe"].fillna(0).sum()
            total_haber = df_valido["Haber"].fillna(0).sum()
            diferencia = abs(total_debe - total_haber)
            balanceado = diferencia < 0.01  # Tolerancia para flotantes

            st.markdown("---")

            col_d, col_h, col_b = st.columns(3)
            with col_d:
                st.metric("📥 Total Debe (entradas)", f"{total_debe:,.2f} lb")
            with col_h:
                st.metric("📤 Total Haber (salidas)", f"{total_haber:,.2f} lb")
            with col_b:
                if balanceado:
                    st.metric("⚖️ Balance", "✅ Balanceado")
                else:
                    st.metric("⚖️ Diferencia", f"⚠️ {diferencia:,.2f} lb")

            if not balanceado:
                st.warning(
                    f"La partida no está balanceada. "
                    f"Debe = {total_debe:,.2f} lb, Haber = {total_haber:,.2f} lb. "
                    f"Diferencia: {diferencia:,.2f} lb."
                )

            # ── Validaciones adicionales ─────────────────────────────
            errores_partida = []
            for _, row in df_valido.iterrows():
                debe_val = row["Debe"] if pd.notna(row["Debe"]) else 0
                haber_val = row["Haber"] if pd.notna(row["Haber"]) else 0
                if debe_val > 0 and haber_val > 0:
                    errores_partida.append(
                        f"'{row['Producto']}' tiene valores en Debe y Haber. "
                        "Cada línea debe tener valor solo en uno de los dos."
                    )
                if debe_val == 0 and haber_val == 0:
                    errores_partida.append(
                        f"'{row['Producto']}' no tiene peso en Debe ni en Haber."
                    )

            if total_debe == 0:
                errores_partida.append("Debe haber al menos un producto en el Debe (resultado).")
            if total_haber == 0:
                errores_partida.append("Debe haber al menos un producto en el Haber (consumo).")

            for err in errores_partida:
                st.error(err)

            # ── Botones de acción ────────────────────────────────────
            col_gt, col_lt = st.columns(2)
            with col_gt:
                btn_guardar_tr = st.button(
                    "✅ Guardar Transformación", type="primary",
                    use_container_width=True, key="btn_g_tr",
                    disabled=(not balanceado or len(errores_partida) > 0),
                )
            with col_lt:
                if st.button("🧹 Limpiar partida", use_container_width=True, key="btn_l_tr"):
                    st.session_state.df_transformacion = pd.DataFrame(
                        columns=["Producto", "Debe", "Haber"]
                    )
                    st.rerun()

            if btn_guardar_tr:
                try:
                    for _, row in df_valido.iterrows():
                        sku = sku_map.get(row["Producto"], "")
                        debe_val = float(row["Debe"]) if pd.notna(row["Debe"]) and row["Debe"] > 0 else None
                        haber_val = float(row["Haber"]) if pd.notna(row["Haber"]) and row["Haber"] > 0 else None
                        insertar_movimiento(id_mov, sku, fecha_transf, debe_val, haber_val)

                    st.success(f"✅ Transformación **{id_mov}** registrada exitosamente.")
                    get_movimientos_recientes.clear()
                    st.balloons()
                    time.sleep(2)
                    st.session_state.df_transformacion = pd.DataFrame(
                        columns=["Producto", "Debe", "Haber"]
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al guardar: {e}")
    else:
        st.info("Agregue filas a la partida usando el botón + en la tabla de arriba.")


# ══════════════════════════════════════════════════════════════════════
# TAB 3 – HISTORIAL DE MOVIMIENTOS
# ══════════════════════════════════════════════════════════════════════
with tab_historial:
    st.subheader("Últimos movimientos registrados")

    if st.button("🔄 Actualizar historial"):
        get_movimientos_recientes.clear()
        st.rerun()

    df_hist = get_movimientos_recientes()

    if df_hist.empty:
        st.info("No hay movimientos registrados aún.")
    else:
        st.dataframe(
            df_hist,
            use_container_width=True,
            hide_index=True,
            column_config={
                "ID_Movimiento": st.column_config.TextColumn("ID Movimiento"),
                "Fecha": st.column_config.DateColumn("Fecha"),
                "Producto": st.column_config.TextColumn("Producto"),
                "SKU": st.column_config.TextColumn("SKU"),
                "Debe": st.column_config.NumberColumn("Debe (lb)", format="%.2f"),
                "Haber": st.column_config.NumberColumn("Haber (lb)", format="%.2f"),
            },
        )
