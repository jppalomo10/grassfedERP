import streamlit as st
import pandas as pd
import numpy as np
from db import run_query
from auth import check_login, role_badge, require_min_role

st.set_page_config(
    page_title="Carga Masiva",
    page_icon="📤",
    layout="wide",
)

if not check_login():
    st.stop()

require_min_role("dev")

st.sidebar.markdown(f"**{st.session_state.user}** · {role_badge()}")
if st.sidebar.button("Cerrar Sesión"):
    for key in ["authenticated", "user", "role"]:
        st.session_state.pop(key, None)
    st.rerun()

# ── Configuración de tablas ───────────────────────────────────────────────────
TABLE_CONFIG = {
    "Clientes": {
        "pk": ["Teléfono"],
        "columns": ["Teléfono", "Nombre", "Dirección", "Correo", "NIT"],
        "required": ["Teléfono", "Nombre", "Dirección"],
        "defaults": {"NIT": "CF"},
    },
    "Productos": {
        "pk": ["SKU"],
        "columns": ["SKU", "Producto", "Precio"],
        "required": ["SKU", "Producto"],
        "defaults": {},
    },
    "Pedidos": {
        "pk": ["ID_Pedido"],
        "columns": ["ID_Pedido", "Fecha", "Cliente", "Total", "Estado", "Pago", "Envío", "Entregado"],
        "required": ["ID_Pedido", "Fecha", "Cliente", "Total", "Pago"],
        "defaults": {"Estado": "Pendiente de Pago", "Entregado": False},
    },
    "DetallePedido": {
        "pk": ["ID_Pedido", "SKU"],
        "columns": ["ID_Pedido", "SKU", "Cantidad", "Peso", "Precio", "Descuento", "Subtotal"],
        "required": ["ID_Pedido", "SKU", "Peso", "Precio", "Subtotal"],
        "defaults": {},
    },
    "MovimientosInventario": {
        "pk": ["ID_Movimiento"],
        "columns": ["ID_Movimiento", "SKU", "Fecha", "Debe", "Haber"],
        "required": ["ID_Movimiento", "SKU", "Fecha"],
        "defaults": {},
    },
    "InventarioHistórico": {
        "pk": ["Fecha", "SKU"],
        "columns": ["Fecha", "SKU", "Peso"],
        "required": ["Fecha", "SKU", "Peso"],
        "defaults": {},
    },
    "AsientosContables": {
        "pk": ["id"],
        "columns": ["id", "Fecha", "Cuenta", "Debe", "Haber", "Comentarios"],
        "required": ["id", "Fecha", "Cuenta"],
        "defaults": {},
    },
    "CatálogoCuentas": {
        "pk": ["ID_Cuenta"],
        "columns": ["ID_Cuenta", "Nombre", "Tipo"],
        "required": ["ID_Cuenta", "Nombre", "Tipo"],
        "defaults": {},
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────
def to_python_value(val):
    """Convierte valores de pandas/numpy a tipos nativos de Python para psycopg2."""
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return float(val)
    if isinstance(val, pd.Timestamp):
        return val.date()
    if isinstance(val, (np.bool_,)):
        return bool(val)
    return val


def get_existing_pks(table_name, pk_cols):
    """Devuelve el conjunto de PKs existentes en la tabla."""
    quoted_pks = ", ".join([f'"{c}"' for c in pk_cols])
    rows = run_query(f'SELECT {quoted_pks} FROM public."{table_name}"')
    if not rows:
        return set()
    if len(pk_cols) == 1:
        return {str(row[pk_cols[0]]) for row in rows}
    return {tuple(str(row[c]) for c in pk_cols) for row in rows}


def row_pk_key(row, pk_cols):
    if len(pk_cols) == 1:
        return str(row[pk_cols[0]])
    return tuple(str(row[c]) for c in pk_cols)


def insert_rows(table_name, df, columns):
    """Inserta las filas del dataframe en la tabla. Retorna (insertadas, errores)."""
    quoted_table = f'public."{table_name}"'
    quoted_cols = ", ".join([f'"{c}"' for c in columns])
    placeholders = ", ".join(["%s"] * len(columns))
    sql = f"INSERT INTO {quoted_table} ({quoted_cols}) VALUES ({placeholders})"

    inserted = 0
    errors = []

    for _, row in df.iterrows():
        values = tuple(to_python_value(row.get(col)) for col in columns)
        try:
            run_query(sql, values, fetch="none")
            inserted += 1
        except Exception as e:
            errors.append(str(e))

    return inserted, errors


# ── UI ────────────────────────────────────────────────────────────────────────
st.title("📤 Carga Masiva")
st.markdown("Importa registros desde un archivo Excel directamente a la base de datos.")

table_name = st.selectbox("Tabla destino:", list(TABLE_CONFIG.keys()))
config = TABLE_CONFIG[table_name]

with st.expander("📋 Ver columnas esperadas para esta tabla"):
    meta_df = pd.DataFrame({
        "Columna": config["columns"],
        "Obligatoria": ["Sí" if c in config["required"] else "No" for c in config["columns"]],
        "Clave Primaria": ["Sí" if c in config["pk"] else "No" for c in config["columns"]],
    })
    st.dataframe(meta_df, use_container_width=True, hide_index=True)

st.divider()

uploaded_file = st.file_uploader(
    "Sube tu archivo Excel (.xlsx / .xls)",
    type=["xlsx", "xls"],
    key=f"uploader_{table_name}",
)

if uploaded_file:
    # ── Leer archivo ──────────────────────────────────────────────────────────
    try:
        df_raw = pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"Error al leer el archivo: {e}")
        st.stop()

    # ── Validar columnas requeridas ───────────────────────────────────────────
    missing = [c for c in config["required"] if c not in df_raw.columns]
    if missing:
        st.error(f"Faltan columnas obligatorias: **{', '.join(missing)}**")
        st.info(f"Columnas encontradas en el archivo: `{', '.join(df_raw.columns.tolist())}`")
        st.stop()

    # ── Aplicar valores por defecto para columnas opcionales ausentes ─────────
    for col, default in config["defaults"].items():
        if col not in df_raw.columns:
            df_raw[col] = default

    # ── Conservar solo columnas conocidas en el orden del DDL ─────────────────
    valid_cols = [c for c in config["columns"] if c in df_raw.columns]
    df = df_raw[valid_cols].copy()

    # ── Preview ───────────────────────────────────────────────────────────────
    st.subheader("Vista previa del archivo")
    st.dataframe(df, use_container_width=True)
    st.caption(f"{len(df)} filas detectadas en el archivo")

    st.divider()

    # ── Verificación de duplicados ────────────────────────────────────────────
    with st.spinner("Verificando duplicados contra la base de datos…"):
        try:
            existing_pks = get_existing_pks(table_name, config["pk"])
        except Exception as e:
            st.error(f"No se pudo consultar la base de datos: {e}")
            st.stop()

    is_dup = df.apply(lambda r: row_pk_key(r, config["pk"]) in existing_pks, axis=1)
    df_dupes = df[is_dup]
    df_new = df[~is_dup].copy()

    col1, col2 = st.columns(2)
    col1.metric("Filas nuevas a insertar", len(df_new), delta=None)
    col2.metric("Filas duplicadas (serán omitidas)", len(df_dupes), delta=None)

    if len(df_dupes) > 0:
        with st.expander(f"⚠️ {len(df_dupes)} fila(s) duplicada(s) — ya existen en la BD y serán omitidas"):
            pk_label = " + ".join(config["pk"])
            st.caption(f"Criterio de duplicado: **{pk_label}**")
            st.dataframe(df_dupes, use_container_width=True)

    st.divider()

    if len(df_new) == 0:
        st.warning("No hay filas nuevas para insertar. Todos los registros del archivo ya existen en la base de datos.")
    else:
        st.success(f"Se insertarán **{len(df_new)}** fila(s) nueva(s) en **{table_name}**.")

        if st.button("⬆️ Cargar datos", type="primary", use_container_width=True):
            with st.spinner(f"Insertando {len(df_new)} registro(s)…"):
                inserted, errors = insert_rows(table_name, df_new, valid_cols)

            if errors:
                st.error(f"Se insertaron **{inserted}** filas, pero ocurrieron **{len(errors)}** error(es):")
                for err in errors[:10]:
                    st.code(err)
                if len(errors) > 10:
                    st.caption(f"… y {len(errors) - 10} errores más.")
            else:
                st.success(f"✅ **{inserted}** registro(s) cargado(s) exitosamente en **{table_name}**.")
                st.balloons()
