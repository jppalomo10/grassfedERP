import streamlit as st
import pandas as pd
import time
from datetime import date
from decimal import Decimal
from db import run_query
from auth import check_login, role_badge
from pdf_utils import generar_factura_pdf, costos_envio

# ── Configuración de promociones ─────────────────────────────────────
BUNDLE_CONFIGS = {
    "Value Box": {
        "box_sku": "P0001",
        "box_precio": 535.0,
        "componentes": [
            {"SKU": "20004", "Producto": "Bistec / Milanesa",  "Peso (lb)": 1.2, "Cantidad": 1},
            {"SKU": "30005", "Producto": "Cocer",              "Peso (lb)": 1.2,  "Cantidad": 1},
            {"SKU": "30008", "Producto": "Guisar",             "Peso (lb)": 1.2,  "Cantidad": 1},
            {"SKU": "20002", "Producto": "Asar",               "Peso (lb)": 1.2,  "Cantidad": 1},
            {"SKU": "40006", "Producto": "Costilla",           "Peso (lb)": 2.0,  "Cantidad": 1},
            {"SKU": "40013", "Producto": "Hueso Mixto",        "Peso (lb)": 2.0,  "Cantidad": 1},
            {"SKU": "30011", "Producto": "Molida 80/20",       "Peso (lb)": 2.0,  "Cantidad": 1},
            {"SKU": "50002", "Producto": "Pollo",              "Peso (lb)": 5.0,  "Cantidad": 1},
        ],
    },
    "Premium Box": {
        "box_sku": "P0002",
        "box_precio": 655.0,
        "componentes": [
            {"SKU": "10003", "Producto": "Lomito Porcionado",  "Peso (lb)": 1.2, "Cantidad": 1},
            {"SKU": "10008", "Producto": "Rib Eye c/hueso",    "Peso (lb)": 1.2, "Cantidad": 1},
            {"SKU": "10010", "Producto": "Manita de rochoy",   "Peso (lb)": 1.2,  "Cantidad": 1},
            {"SKU": "10001", "Producto": "Bolovique",          "Peso (lb)": 1.2, "Cantidad": 1},
            {"SKU": "40006", "Producto": "Costilla",           "Peso (lb)": 2.0,  "Cantidad": 1},
            {"SKU": "40013", "Producto": "Hueso Mixto",        "Peso (lb)": 2.0,  "Cantidad": 1},
            {"SKU": "10005", "Producto": "Molida Magra",       "Peso (lb)": 2.0,  "Cantidad": 1},
            {"SKU": "50002", "Producto": "Pollo",              "Peso (lb)": 5.0,  "Cantidad": 1},
        ],
    },
}

# ── Configuración de página ──────────────────────────────────────────
st.set_page_config(
    page_title="Registro de Pedidos",
    page_icon="📋",
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

# ── Inicializar estado ───────────────────────────────────────────────
if "lineas" not in st.session_state:
    st.session_state.lineas = []  # lista de dicts con las líneas de detalle

# ── Helpers de datos ─────────────────────────────────────────────────
@st.cache_data(ttl=120)
def get_clientes():
    """Devuelve DataFrame con todos los clientes."""
    rows = run_query(
        'SELECT "Teléfono", "Nombre", "Dirección", COALESCE("NIT", \'C/F\') AS "NIT" FROM "Clientes" ORDER BY "Nombre"'
    )
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["Teléfono", "Nombre", "Dirección", "NIT"]
    )


@st.cache_data(ttl=120)
def get_productos():
    """Devuelve DataFrame con todos los productos."""
    rows = run_query(
        'SELECT "SKU", "Producto", "Precio" FROM "Productos" ORDER BY "Producto"'
    )
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["SKU", "Producto", "Precio"]
    )


def get_next_id_pedido():
    """Obtiene el siguiente ID de pedido disponible."""
    row = run_query(
        'SELECT COALESCE(MAX("ID_Pedido"), 0) + 1 AS next_id FROM "Pedidos"',
        fetch="one",
    )
    return row["next_id"]


def insertar_pedido(id_pedido, fecha, cliente_tel, total, pago, envio):
    """Inserta un registro en la tabla Pedidos."""
    run_query(
        """
        INSERT INTO "Pedidos" ("ID_Pedido", "Fecha", "Cliente", "Total", "Pago", "Envío")
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        params=(id_pedido, fecha, cliente_tel, total, pago, envio),
        fetch="none",
    )


def insertar_detalle(id_pedido, sku, peso, precio, descuento, subtotal, cantidad):
    """Inserta una línea en DetallePedido."""
    run_query(
        """
        INSERT INTO "DetallePedido"
            ("ID_Pedido", "SKU", "Peso", "Precio", "Descuento", "Subtotal", "Cantidad")
        OVERRIDING SYSTEM VALUE
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        params=(id_pedido, sku, peso, precio, descuento, subtotal, cantidad),
        fetch="none",
    )


def insertar_cliente(telefono, nombre, direccion, nit):
    """Inserta un nuevo cliente."""
    run_query(
        """
        INSERT INTO "Clientes" ("Teléfono", "Nombre", "Dirección", "NIT")
        VALUES (%s, %s, %s, %s)
        """,
        params=(telefono, nombre, direccion, nit),
        fetch="none",
    )


def agregar_bundle(nombre_bundle: str):
    cfg = BUNDLE_CONFIGS[nombre_bundle]
    st.session_state.lineas.append({
        "SKU": cfg["box_sku"],
        "Producto": nombre_bundle,
        "Cantidad": 1,
        "Peso (lb)": 1.0,
        "Precio": cfg["box_precio"],
        "Descuento (%)": 0.0,
        "Subtotal": cfg["box_precio"],
    })
    for comp in cfg["componentes"]:
        st.session_state.lineas.append({
            "SKU": comp["SKU"],
            "Producto": comp["Producto"],
            "Cantidad": comp["Cantidad"],
            "Peso (lb)": comp["Peso (lb)"],
            "Precio": 0.0,
            "Descuento (%)": 0.0,
            "Subtotal": 0.0,
        })


# ── Cargar catálogos ─────────────────────────────────────────────────
df_clientes = get_clientes()
df_productos = get_productos()

# ── Título ───────────────────────────────────────────────────────────
st.title("📋 Registro de Pedidos")
st.divider()

# ══════════════════════════════════════════════════════════════════════
# SECCIÓN 1 – DATOS DEL PEDIDO
# ══════════════════════════════════════════════════════════════════════
st.subheader("Datos del pedido")

col_fecha, col_modo = st.columns(2)

with col_fecha:
    fecha = st.date_input("📅 Fecha", value=date.today())

with col_modo:
    modo_cliente = st.radio(
        "Cliente",
        ["Existente", "Nuevo"],
        horizontal=True,
    )

# ── Selector de cliente ──────────────────────────────────────────────
if modo_cliente == "Existente":
    if df_clientes.empty:
        st.info("No hay clientes registrados. Registre uno nuevo.")
        cliente_tel = None
    else:
        opciones = df_clientes.apply(
                lambda r: f"{r['Nombre']}  ({r['Teléfono']})", axis=1
            ).tolist()
        seleccion = st.selectbox("Seleccionar cliente", [""] + opciones)
        # Extraer teléfono del texto seleccionado
        cliente_tel = seleccion.split("(")[-1].rstrip(")") if seleccion else None
        direccion_cli = df_clientes.loc[
            df_clientes["Teléfono"] == cliente_tel, "Dirección"
        ]
        if cliente_tel and not direccion_cli.empty:
            st.markdown(f"**Dirección del Cliente:** {direccion_cli.values[0]}")
        else:
            st.markdown("**Dirección del Cliente:** —")
else:
    c1, c2 = st.columns(2)
    nuevo_tel = c1.text_input("Teléfono *")
    nuevo_nit = c2.text_input("NIT *")
    nuevo_nombre = st.text_input("Nombre *")
    nueva_dir = st.text_input("Dirección *")
    cliente_tel = nuevo_tel  # se usará al guardar
    nuevo_nombre = nuevo_nombre.upper()

col_pago, col_envio = st.columns(2)

with col_pago:
    metodo_pago = st.selectbox(
        "💳 Método de pago",
        ["", "Efectivo", "Transferencia", "Tarjeta"],
    )

with col_envio:
    envio = st.selectbox(
        "📦 Envío",
        ["", "Ciudad", "Antigua Guatemala", "Metropolitano", "Gratis"],
    )

st.divider()

# ══════════════════════════════════════════════════════════════════════
# SECCIÓN 2 – AGREGAR LÍNEAS DE DETALLE
# ══════════════════════════════════════════════════════════════════════
st.subheader("Detalle del pedido")

if df_productos.empty:
    st.warning("No hay productos en el catálogo.")
else:
    with st.expander("🎁 Agregar Promoción", expanded=False):
        st.caption("Agrega todos los productos de la caja de una sola vez. Los componentes se registran con precio Q0 para control de inventario.")
        col_vb, col_pb = st.columns(2)
        with col_vb:
            if st.button("📦 Value Box  —  Q535", use_container_width=True):
                agregar_bundle("Value Box")
                st.rerun()
        with col_pb:
            if st.button("⭐ Premium Box  —  Q655", use_container_width=True):
                agregar_bundle("Premium Box")
                st.rerun()

    with st.expander("➕ Agregar producto al pedido", expanded=True):
        cp1, cp2, cp3, cp4 = st.columns([3, 1, 1, 1])

        with cp1:
            opciones_prod = df_productos.apply(
                lambda r: f"{r['Producto']}  (SKU: {r['SKU']})", axis=1
            ).tolist()
            prod_sel = st.selectbox("Producto", [""] + opciones_prod, key="sel_prod")
            if prod_sel:
                sku_sel = prod_sel.split("SKU: ")[-1].rstrip(")")
                precio_unitario = float(
                    df_productos.loc[
                        df_productos["SKU"] == sku_sel, "Precio"
                    ].values[0]
                )
            else:
                sku_sel = None
                precio_unitario = 0.0

        with cp2:
            cantidad = st.number_input("Cantidad", min_value=1, value=1, step=1, key="cant")

        with cp3:
            peso = st.number_input("Peso (lb)", min_value=0.0, value=1.0, step=0.25, format="%.2f", key="peso")

        with cp4:
            descuento = st.number_input(
                "Descuento (Q)", min_value=0.0,
                value=0.0, step=1.0, format="%.1f", key="desc",
            )

        # Cálculo de subtotal en vivo
        subtotal_linea = round(precio_unitario * peso  - descuento, 2)
        st.markdown(
            f"**Precio unitario:** Q{precio_unitario:,.2f} &nbsp;|&nbsp; "
            f"**Subtotal:** Q{subtotal_linea:,.2f}"
        )

        if st.button("➕ Agregar línea", type="primary", disabled=(not prod_sel)):
            st.session_state.lineas.append(
                {
                    "SKU": sku_sel,
                    "Producto": prod_sel.split("  (SKU")[0],
                    "Cantidad": cantidad,
                    "Peso (lb)": peso,
                    "Precio": precio_unitario,
                    "Descuento (%)": descuento,
                    "Subtotal": subtotal_linea,
                }
            )
            st.rerun()

# ── Tabla de líneas agregadas ────────────────────────────────────────
if st.session_state.lineas:
    st.markdown("#### 🛒 Líneas del pedido")
    df_lineas = pd.DataFrame(st.session_state.lineas)
    st.dataframe(
        df_lineas,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Precio (Q)": st.column_config.NumberColumn(format="Q%.2f"),
            "Subtotal (Q)": st.column_config.NumberColumn(format="Q%.2f"),
            "Descuento (Q)": st.column_config.NumberColumn(format="%.1f%%"),
            "Peso (lb)": st.column_config.NumberColumn(format="%.2f"),
        },
    )


    # Botones para eliminar líneas
    cols_del = st.columns(len(st.session_state.lineas))
    for i, col in enumerate(cols_del):
        with col:
            if st.button(f"🗑️ Quitar #{i+1}", key=f"del_{i}"):
                st.session_state.lineas.pop(i)
                st.rerun()

    envio_costo = costos_envio.get(envio, 0)
    st.markdown(f"Costo de envío: **Q{envio_costo:,.2f}**")

    total_pedido = sum(l["Subtotal"] for l in st.session_state.lineas) + envio_costo
    st.markdown(f"### 💰 Total del pedido: **Q{total_pedido:,.2f}**")
else:
    st.info("Aún no ha agregado productos al pedido.")
    total_pedido = 0

# ── Botones ──────────────────────────────────────────────────────────
col_guardar, col_limpiar, col_pdf = st.columns(3)

with col_guardar:
    btn_guardar = st.button(
        "✅ Guardar Pedido", type="primary", use_container_width=True,
        disabled=(len(st.session_state.lineas) == 0),
    )

with col_limpiar:
    if st.button("🧹 Limpiar formulario", use_container_width=True):
        st.session_state.lineas = []
        st.rerun()

with col_pdf:
    id_pedido = get_next_id_pedido()

    # Obtener nombre, dirección y NIT según el modo de cliente
    if modo_cliente == "Existente" and cliente_tel:
        match = df_clientes.loc[df_clientes["Teléfono"] == cliente_tel]
        if not match.empty:
            cliente_nombre = match["Nombre"].iloc[0].replace(" ", "")
            cliente_dir = match["Dirección"].iloc[0]
            cliente_nit = match["NIT"].iloc[0]
        else:
            cliente_nombre = None
            cliente_dir = None
            cliente_nit = "C/F"
    elif modo_cliente == "Nuevo" and nuevo_nombre:
        cliente_nombre = nuevo_nombre.strip().replace(" ", "")
        cliente_dir = nueva_dir.strip() if nueva_dir else ""
        cliente_nit = nuevo_nit.strip() if nuevo_nit else "C/F"
    else:
        cliente_nombre = None
        cliente_dir = None
        cliente_nit = "C/F"

    if cliente_nombre and st.session_state.lineas:
        st.download_button(
            label="📄 Descargar Factura PDF",
            data=generar_factura_pdf(
                id_pedido, fecha,
                cliente_nombre,
                cliente_tel,
                cliente_dir, metodo_pago,
                st.session_state.lineas, total_pedido, envio,
                cliente_nit=cliente_nit,
            ),
            file_name=f"Factura_{id_pedido}_{cliente_nombre}.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True,
        )
    else:
        st.button(
            "📄 Descargar Factura PDF",
            disabled=True,
            use_container_width=True,
        )

if btn_guardar:
    # ── Validaciones ─────────────────────────────────────────────────
    errores = []
    if not cliente_tel:
        errores.append("Debe seleccionar o registrar un cliente.")
    if modo_cliente == "Nuevo" and (not nuevo_tel or not nuevo_nombre or not nueva_dir):
        errores.append("Complete todos los campos del nuevo cliente (Teléfono, Nombre, Dirección).")
    if not metodo_pago:
        errores.append("Seleccione un método de pago.")
    if not envio:
        errores.append("Seleccione un tipo de envío.")
    if not st.session_state.lineas:
        errores.append("Agregue al menos una línea de detalle.")

    if errores:
        for e in errores:
            st.error(e)
    else:
        try:
            # 1. Si es cliente nuevo, insertarlo primero
            if modo_cliente == "Nuevo":
                insertar_cliente(nuevo_tel.strip(), nuevo_nombre.strip(), nueva_dir.strip(), nuevo_nit.strip())
                get_clientes.clear()  # limpiar caché

            # 2. Obtener siguiente ID
            id_pedido = get_next_id_pedido()

            # 3. Insertar pedido
            insertar_pedido(
                id_pedido, fecha, cliente_tel.strip(),
                Decimal(str(total_pedido)), metodo_pago, envio  
            )

            # 4. Insertar cada línea de detalle
            for linea in st.session_state.lineas:
                insertar_detalle(
                    id_pedido,
                    linea["SKU"],
                    linea["Peso (lb)"],
                    Decimal(str(linea["Precio"])),
                    Decimal(str(linea["Descuento (%)"])),
                    Decimal(str(linea["Subtotal"])),
                    linea["Cantidad"],
                )

            st.success(f"✅ Pedido **#{id_pedido}** guardado exitosamente.")
            st.balloons()            
            time.sleep(2)
            st.session_state.lineas = []
            st.rerun()

        except Exception as e:
            st.error(f"Error al guardar el pedido: {str(e)}")
