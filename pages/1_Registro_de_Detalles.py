import streamlit as st
import pandas as pd
import time
from datetime import date
from decimal import Decimal
from io import BytesIO
from fpdf import FPDF
from db import run_query
from auth import check_login, role_badge

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
        'SELECT "Teléfono", "Nombre", "Dirección" FROM "Clientes" ORDER BY "Nombre"'
    )
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["Teléfono", "Nombre", "Dirección"]
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


def insertar_pedido(id_pedido, fecha, cliente_tel, total, pago):
    """Inserta un registro en la tabla Pedidos."""
    run_query(
        """
        INSERT INTO "Pedidos" ("ID_Pedido", "Fecha", "Cliente", "Total", "Pago")
        VALUES (%s, %s, %s, %s, %s)
        """,
        params=(id_pedido, fecha, cliente_tel, total, pago),
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


def insertar_cliente(telefono, nombre, direccion):
    """Inserta un nuevo cliente."""
    run_query(
        """
        INSERT INTO "Clientes" ("Teléfono", "Nombre", "Dirección")
        VALUES (%s, %s, %s)
        """,
        params=(telefono, nombre, direccion),
        fetch="none",
    )


def generar_factura_pdf(id_pedido, fecha, cliente_nombre, cliente_tel,
                        cliente_dir, metodo_pago, lineas, total):
    """Genera un PDF tipo factura y devuelve los bytes."""

    # ── Colores de marca ─────────────────────────────────────────────
    VERDE = (84, 98, 50)       # #546232
    MARRON = (26, 21, 16)      # #1A1510
    BEIGE = (235, 223, 199)    # #EBDFC7
    BLANCO = (255, 255, 255)
    GRIS_CLARO = (245, 240, 233)

    pdf = FPDF(orientation="P", unit="mm", format="Letter")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    page_w = pdf.w - 2 * pdf.l_margin  # ancho útil

    # ── Encabezado con banda verde ───────────────────────────────────
    pdf.set_fill_color(*VERDE)
    pdf.rect(0, 0, pdf.w, 38, "F")

    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(*BLANCO)
    pdf.set_xy(pdf.l_margin, 8)
    pdf.cell(page_w / 2, 10, "GrassFed GT", ln=0)

    pdf.set_font("Helvetica", "", 11)
    pdf.set_xy(pdf.l_margin + page_w / 2, 8)
    pdf.cell(page_w / 2, 6, f"Factura  #{id_pedido}", align="R", ln=1)
    pdf.set_x(pdf.l_margin + page_w / 2)
    pdf.cell(page_w / 2, 6, f"Fecha: {fecha.strftime('%d/%m/%Y')}", align="R", ln=1)
    pdf.set_x(pdf.l_margin + page_w / 2)
    pdf.cell(page_w / 2, 6, f"Pago: {metodo_pago}", align="R", ln=1)

    pdf.ln(12)

    # ── Datos del cliente ────────────────────────────────────────────
    pdf.set_text_color(*MARRON)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(page_w, 7, "Datos del cliente", ln=1)
    pdf.set_draw_color(*VERDE)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + page_w, pdf.get_y())
    pdf.ln(3)

    pdf.set_font("Helvetica", "", 10)
    labels = ["Nombre:", "Telefono:", "Direccion:"]
    values = [cliente_nombre, cliente_tel, cliente_dir]
    for lab, val in zip(labels, values):
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(28, 6, lab)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, str(val), ln=1)

    pdf.ln(6)

    # ── Tabla de detalle ─────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(page_w, 7, "Detalle de productos", ln=1)
    pdf.set_draw_color(*VERDE)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + page_w, pdf.get_y())
    pdf.ln(3)

    # Anchos de columnas  (total = page_w)
    col_w = [
        page_w * 0.08,   # #
        page_w * 0.30,   # Producto
        page_w * 0.12,   # Cantidad
        page_w * 0.12,   # Peso
        page_w * 0.13,   # Precio
        page_w * 0.12,   # Descuento
        page_w * 0.13,   # Subtotal
    ]
    headers = ["#", "Producto", "Cant.", "Peso (lb)", "Precio", "Desc. (Q)", "Subtotal"]

    # Cabecera de tabla
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(*VERDE)
    pdf.set_text_color(*BLANCO)
    for i, h in enumerate(headers):
        align = "C" if i > 1 else "L"
        pdf.cell(col_w[i], 8, h, border=0, align=align, fill=True)
    pdf.ln()

    # Filas
    pdf.set_text_color(*MARRON)
    pdf.set_font("Helvetica", "", 9)
    for idx, l in enumerate(lineas, 1):
        fill = idx % 2 == 0
        if fill:
            pdf.set_fill_color(*GRIS_CLARO)
        pdf.cell(col_w[0], 7, str(idx), border=0, fill=fill)
        pdf.cell(col_w[1], 7, str(l["Producto"]), border=0, fill=fill)
        pdf.cell(col_w[2], 7, str(l["Cantidad"]), border=0, align="C", fill=fill)
        pdf.cell(col_w[3], 7, f"{l['Peso (lb)']:.2f}", border=0, align="C", fill=fill)
        pdf.cell(col_w[4], 7, f"Q{l['Precio']:,.2f}", border=0, align="R", fill=fill)
        pdf.cell(col_w[5], 7, f"Q{l['Descuento (%)']:,.2f}", border=0, align="R", fill=fill)
        pdf.cell(col_w[6], 7, f"Q{l['Subtotal']:,.2f}", border=0, align="R", fill=fill)
        pdf.ln()

    # Línea separadora
    pdf.set_draw_color(*VERDE)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + page_w, pdf.get_y())
    pdf.ln(3)

    # Total
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(page_w - col_w[-1], 9, "TOTAL:", align="R")
    pdf.set_fill_color(*VERDE)
    pdf.set_text_color(*BLANCO)
    pdf.cell(col_w[-1], 9, f"Q{total:,.2f}", align="R", fill=True)
    pdf.ln(12)

    # ── Pie de página ────────────────────────────────────────────────
    pdf.set_text_color(140, 140, 140)
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(page_w, 5, "GrassFed GT  |  Carne 100% libre de hormonas  |  grassfedgt.com", align="C")

    # Exportar a bytes
    buf = BytesIO()
    buf.write(pdf.output())
    buf.seek(0)
    return buf


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

col_fecha, col_pago = st.columns(2)

with col_fecha:
    fecha = st.date_input("📅 Fecha", value=date.today())

with col_pago:
    metodo_pago = st.selectbox(
        "💳 Método de pago",
        ["Efectivo", "Transferencia", "Tarjeta"],
    )

# ── Selector de cliente ──────────────────────────────────────────────
modo_cliente = st.radio(
    "Cliente",
    ["Existente", "Nuevo"],
    horizontal=True,
    label_visibility="collapsed",
    )

if modo_cliente == "Existente":
    if df_clientes.empty:
        st.info("No hay clientes registrados. Registre uno nuevo.")
        cliente_tel = None
    else:
        opciones = df_clientes.apply(
                lambda r: f"{r['Nombre']}  ({r['Teléfono']})", axis=1
            ).tolist()
        seleccion = st.selectbox("Seleccionar cliente", opciones)
        # Extraer teléfono del texto seleccionado
        cliente_tel = seleccion.split("(")[-1].rstrip(")")
else:
    c1, c2 = st.columns(2)
    nuevo_tel = c1.text_input("Teléfono *")
    nuevo_nombre = c2.text_input("Nombre *")
    nueva_dir = st.text_input("Dirección *")
    cliente_tel = nuevo_tel  # se usará al guardar
    nuevo_nombre = nuevo_nombre.upper()

st.divider()

# ══════════════════════════════════════════════════════════════════════
# SECCIÓN 2 – AGREGAR LÍNEAS DE DETALLE
# ══════════════════════════════════════════════════════════════════════
st.subheader("Detalle del pedido")

if df_productos.empty:
    st.warning("No hay productos en el catálogo.")
else:
    with st.expander("➕ Agregar producto al pedido", expanded=False):
        cp1, cp2, cp3, cp4 = st.columns([3, 1, 1, 1])

        with cp1:
            opciones_prod = df_productos.apply(
                lambda r: f"{r['Producto']}  (SKU: {r['SKU']})", axis=1
            ).tolist()
            prod_sel = st.selectbox("Producto", opciones_prod, key="sel_prod")
            sku_sel = prod_sel.split("SKU: ")[-1].rstrip(")")
            precio_unitario = float(
                df_productos.loc[
                    df_productos["SKU"] == sku_sel, "Precio"
                ].values[0]
            )

        with cp2:
            cantidad = st.number_input("Cantidad", min_value=1, value=1, step=1, key="cant")

        with cp3:
            peso = st.number_input("Peso (lb)", min_value=0.0, value=1.0, step=0.25, format="%.2f", key="peso")

        with cp4:
            descuento = st.number_input(
                "Descuento (Q)", min_value=0.0, max_value=100.0,
                value=0.0, step=1.0, format="%.1f", key="desc",
            )

        # Cálculo de subtotal en vivo
        subtotal_linea = round(precio_unitario * cantidad * peso  - descuento, 2)
        st.markdown(
            f"**Precio unitario:** Q{precio_unitario:,.2f} &nbsp;|&nbsp; "
            f"**Subtotal:** Q{subtotal_linea:,.2f}"
        )

        if st.button("➕ Agregar línea", type="primary"):
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

    total_pedido = sum(l["Subtotal"] for l in st.session_state.lineas)
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
    st.download_button(
        label="📄 Descargar Factura PDF",
        data=generar_factura_pdf(id_pedido, fecha, 
                        df_clientes.loc[df_clientes["Teléfono"] == cliente_tel, "Nombre"].iloc[0],
                        cliente_tel,
                        df_clientes.loc[df_clientes["Teléfono"] == cliente_tel, "Dirección"].iloc[0], metodo_pago, st.session_state.lineas, total_pedido),
        file_name=f"Factura_{id_pedido}.pdf",
        mime="application/pdf",
        type="primary",
        use_container_width=True,
    )

if btn_guardar:
    # ── Validaciones ─────────────────────────────────────────────────
    errores = []
    if not cliente_tel:
        errores.append("Debe seleccionar o registrar un cliente.")
    if modo_cliente == "Nuevo" and (not nuevo_tel or not nuevo_nombre or not nueva_dir):
        errores.append("Complete todos los campos del nuevo cliente (Teléfono, Nombre, Dirección).")
    if not st.session_state.lineas:
        errores.append("Agregue al menos una línea de detalle.")

    if errores:
        for e in errores:
            st.error(e)
    else:
        try:
            # 1. Si es cliente nuevo, insertarlo primero
            if modo_cliente == "Nuevo":
                insertar_cliente(nuevo_tel.strip(), nuevo_nombre.strip(), nueva_dir.strip())
                get_clientes.clear()  # limpiar caché

            # 2. Obtener siguiente ID
            id_pedido = get_next_id_pedido()

            # 3. Insertar pedido
            insertar_pedido(
                id_pedido, fecha, cliente_tel.strip(),
                Decimal(str(total_pedido)), metodo_pago,
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
