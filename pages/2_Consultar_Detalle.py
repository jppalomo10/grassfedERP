import streamlit as st
import pandas as pd
from db import run_query
from auth import check_login, role_badge
from pdf_utils import generar_factura_pdf, generar_estado_cuenta_pdf, costos_envio
from ui_mensajes import render_seccion_mensaje_cobro


# ── Configuración de página ──────────────────────────────────────────
st.set_page_config(
    page_title="Consultar Detalle",
    page_icon="🔍",
    layout="wide",
)

# ── Autenticación ────────────────────────────────────────────────────
if not check_login():
    st.stop()

st.sidebar.markdown(f"**{st.session_state.user}** · {role_badge()}")
if st.sidebar.button("Cerrar Sesión", key="logout_consulta"):
    for key in ["authenticated", "user", "role"]:
        st.session_state.pop(key, None)
    st.rerun()

# ══════════════════════════════════════════════════════════════════════
# HELPERS DE DATOS
# ══════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=60)
def get_clientes():
    rows = run_query(
        'SELECT "Teléfono", "Nombre", "Dirección", COALESCE("NIT", \'C/F\') AS "NIT" FROM "Clientes" ORDER BY "Nombre"'
    )
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["Teléfono", "Nombre", "Dirección", "NIT"]
    )


def get_pedidos_por_cliente(cliente_tel):
    """Devuelve los pedidos de un cliente dado su teléfono."""
    rows = run_query(
        '''
        SELECT "ID_Pedido", "Fecha", "Total", "Pago", "Envío",
               COALESCE("Estado", 'Pendiente de Pago') AS "Estado",
               COALESCE("Entregado", false) AS "Entregado"
        FROM "Pedidos"
        WHERE "Cliente" = %s
        ORDER BY "ID_Pedido" DESC
        ''',
        params=(cliente_tel,),
    )
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["ID_Pedido", "Fecha", "Total", "Pago", "Envío", "Estado", "Entregado"]
    )


def get_detalle_pedido(id_pedido):
    """Devuelve las líneas de detalle de un pedido."""
    rows = run_query(
        '''
        SELECT dp."SKU", p."Producto", dp."Cantidad",
               dp."Peso", dp."Precio", dp."Descuento", dp."Subtotal"
        FROM "DetallePedido" dp
        JOIN "Productos" p ON dp."SKU" = p."SKU"
        WHERE dp."ID_Pedido" = %s
        ORDER BY dp."SKU"
        ''',
        params=(id_pedido,),
    )
    return rows if rows else []


def get_pedidos_pendientes_cliente(cliente_tel):
    rows = run_query(
        '''
        SELECT "ID_Pedido", "Fecha", "Total"
        FROM "Pedidos"
        WHERE "Cliente" = %s AND "Estado" = 'Pendiente de Pago'
        ORDER BY "Fecha" ASC
        ''',
        params=(cliente_tel,),
    )
    return rows if rows else []


def actualizar_estado(id_pedido, nuevo_estado):
    """Actualiza el estado de un pedido."""
    run_query(
        'UPDATE "Pedidos" SET "Estado" = %s WHERE "ID_Pedido" = %s',
        params=(nuevo_estado, id_pedido),
        fetch="none",
    )


def actualizar_entregado(id_pedido, entregado):
    """Actualiza el campo Entregado de un pedido."""
    run_query(
        'UPDATE "Pedidos" SET "Entregado" = %s WHERE "ID_Pedido" = %s',
        params=(entregado, id_pedido),
        fetch="none",
    )


def actualizar_pago(id_pedido, nuevo_pago):
    """Actualiza el método de pago de un pedido."""
    run_query(
        'UPDATE "Pedidos" SET "Pago" = %s WHERE "ID_Pedido" = %s',
        params=(nuevo_pago, id_pedido),
        fetch="none",
    )


# ══════════════════════════════════════════════════════════════════════
# SIDEBAR – BÚSQUEDA POR CLIENTE
# ══════════════════════════════════════════════════════════════════════
st.sidebar.divider()
st.sidebar.markdown("### 🔍 Buscar facturas")

df_clientes = get_clientes()

if df_clientes.empty:
    st.sidebar.warning("No hay clientes registrados.")
    st.stop()

# Crear opciones de selección de cliente
opciones_clientes = df_clientes.apply(
    lambda r: f"{r['Nombre']}  ({r['Teléfono']})", axis=1
).tolist()

cliente_sel = st.sidebar.selectbox(
    "Seleccionar cliente",
    [""] + opciones_clientes,
    key="consulta_cliente",
)

if not cliente_sel:
    st.info("Seleccione un cliente en la barra lateral para ver sus pedidos.")
    st.stop()

cliente_tel = cliente_sel.split("(")[-1].rstrip(")")
cliente_nombre = df_clientes.loc[
    df_clientes["Teléfono"] == cliente_tel, "Nombre"
].iloc[0]
cliente_dir = df_clientes.loc[
    df_clientes["Teléfono"] == cliente_tel, "Dirección"
].iloc[0]
cliente_nit = df_clientes.loc[
    df_clientes["Teléfono"] == cliente_tel, "NIT"
].iloc[0]

# Obtener pedidos del cliente
df_pedidos = get_pedidos_por_cliente(cliente_tel)

if df_pedidos.empty:
    st.sidebar.info("Este cliente no tiene pedidos.")
    pedido_ids = []
else:
    pedido_ids = df_pedidos["ID_Pedido"].tolist()
    st.sidebar.markdown(f"**{len(pedido_ids)}** factura(s) encontrada(s)")

    # Mapeo ID → Fecha para mostrar en el selectbox
    pedido_fechas = dict(zip(df_pedidos["ID_Pedido"], df_pedidos["Fecha"]))

    def _fmt_factura(x):
        f = pedido_fechas.get(x, "")
        if hasattr(f, "strftime"):
            f = f.strftime("%d/%m/%Y")
        return f"Factura #{x}  ({f})"

    factura_sel = st.sidebar.selectbox(
        "Seleccionar factura",
        pedido_ids,
        format_func=_fmt_factura,
        key="consulta_factura",
    )

    st.sidebar.divider()
    pendientes = get_pedidos_pendientes_cliente(cliente_tel)
    if pendientes:
        pdf_ec = generar_estado_cuenta_pdf(
            cliente_nombre=cliente_nombre,
            cliente_tel=cliente_tel,
            cliente_dir=cliente_dir,
            cliente_nit=cliente_nit,
            pedidos_pendientes=pendientes,
        )
        st.sidebar.download_button(
            label=f"📑 Estado de cuenta ({len(pendientes)} pendiente{'s' if len(pendientes) != 1 else ''})",
            data=pdf_ec,
            file_name=f"EstadoCuenta_{cliente_nombre.replace(' ', '')}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    else:
        st.sidebar.button(
            "📑 Estado de cuenta",
            disabled=True,
            use_container_width=True,
            help="Este cliente no tiene pedidos pendientes de pago",
        )

# ══════════════════════════════════════════════════════════════════════
# CONTENIDO PRINCIPAL
# ══════════════════════════════════════════════════════════════════════
st.title("🔍 Consultar Detalle de Pedido")
st.divider()

if not pedido_ids:
    st.info("Seleccione un cliente con pedidos en la barra lateral para ver los detalles.")
    st.stop()

# ── Datos del pedido seleccionado ────────────────────────────────────
pedido = df_pedidos[df_pedidos["ID_Pedido"] == factura_sel].iloc[0]

# ── Encabezado con info del pedido ───────────────────────────────────
col_info1, col_info2, col_info3, col_info4 = st.columns(4)

with col_info1:
    st.metric("📋 Factura", f"#{pedido['ID_Pedido']}")
with col_info2:
    fecha_display = pedido["Fecha"]
    if hasattr(fecha_display, "strftime"):
        fecha_display = fecha_display.strftime("%d/%m/%Y")
    st.metric("📅 Fecha", str(fecha_display))
with col_info3:
    st.metric("💰 Total", f"Q{float(pedido['Total']):,.2f}")
with col_info4:
    st.metric("💳 Pago", pedido["Pago"])

st.divider()

# ── Datos del cliente ────────────────────────────────────────────────
st.subheader("👤 Datos del cliente")
cc1, cc2, cc3 = st.columns(3)
cc1.markdown(f"**Nombre:** {cliente_nombre}")
cc2.markdown(f"**Teléfono:** {cliente_tel}")
cc3.markdown(f"**Dirección:** {cliente_dir}")

st.divider()

# ── Detalle de productos ────────────────────────────────────────────
st.subheader("📦 Detalle de productos")

detalle = get_detalle_pedido(factura_sel)

if detalle:
    df_detalle = pd.DataFrame(detalle)
    df_detalle.columns = ["SKU", "Producto", "Cantidad", "Peso (lb)", "Precio", "Descuento (Q)", "Subtotal"]

    st.dataframe(
        df_detalle,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Precio": st.column_config.NumberColumn(format="Q%.2f"),
            "Subtotal": st.column_config.NumberColumn(format="Q%.2f"),
            "Descuento (Q)": st.column_config.NumberColumn(format="Q%.2f"),
            "Peso (lb)": st.column_config.NumberColumn(format="%.2f"),
        },
    )

    envio_tipo = pedido["Envío"]
    envio_costo = costos_envio.get(envio_tipo, 0)
    st.markdown(f"**Envío ({envio_tipo}):** Q{envio_costo:,.2f}")
    st.markdown(f"### 💰 Total: Q{float(pedido['Total']):,.2f}")
else:
    st.warning("No se encontraron líneas de detalle para esta factura.")

st.divider()

# ══════════════════════════════════════════════════════════════════════
# SECCIÓN – ACTUALIZAR ESTADO Y ENTREGA
# ══════════════════════════════════════════════════════════════════════
st.subheader("✏️ Actualizar Pedido")

col_estado, col_entrega, col_pago = st.columns(3)

estados_opciones = ["Pendiente de Pago", "Pagado", "Anulado"]
estado_actual = pedido["Estado"]
idx_estado = estados_opciones.index(estado_actual) if estado_actual in estados_opciones else 0

with col_estado:
    nuevo_estado = st.selectbox(
        "📊 Estado del pedido",
        estados_opciones,
        index=idx_estado,
        key=f"estado_{factura_sel}",
    )

entregado_actual = bool(pedido["Entregado"])

with col_entrega:
    nuevo_entregado = st.selectbox(
        "🚚 ¿Entregado?",
        [True, False],
        index=0 if entregado_actual else 1,
        format_func=lambda x: "✅ Sí – Entregado" if x else "❌ No – Pendiente",
        key=f"entregado_{factura_sel}",
    )

pago_opciones = ["Efectivo", "Transferencia", "Tarjeta"]
pago_actual = pedido["Pago"]
idx_pago = pago_opciones.index(pago_actual) if pago_actual in pago_opciones else 0

with col_pago:
    nuevo_pago = st.selectbox(
        "💳 Método de pago",
        pago_opciones,
        index=idx_pago,
        key=f"pago_{factura_sel}",
    )

# Detectar si hubo cambios
cambio_estado = nuevo_estado != estado_actual
cambio_entrega = nuevo_entregado != entregado_actual
cambio_pago = nuevo_pago != pago_actual

col_btn_update, col_btn_pdf = st.columns(2)

with col_btn_update:
    if cambio_estado or cambio_entrega or cambio_pago:
        if st.button("💾 Guardar cambios", type="primary", use_container_width=True):
            try:
                if cambio_estado:
                    actualizar_estado(factura_sel, nuevo_estado)
                if cambio_entrega:
                    actualizar_entregado(factura_sel, nuevo_entregado)
                if cambio_pago:
                    actualizar_pago(factura_sel, nuevo_pago)

                st.success("✅ Pedido actualizado exitosamente.")
                st.rerun()
            except Exception as e:
                st.error(f"Error al actualizar: {str(e)}")
    else:
        st.button(
            "💾 Guardar cambios",
            use_container_width=True,
            disabled=True,
            help="No hay cambios para guardar",
        )

# ══════════════════════════════════════════════════════════════════════
# SECCIÓN – REGENERAR FACTURA PDF
# ══════════════════════════════════════════════════════════════════════
with col_btn_pdf:
    if detalle:
        # Preparar las líneas en el formato esperado por generar_factura_pdf
        lineas_pdf = []
        for d in detalle:
            lineas_pdf.append({
                "Producto": d["Producto"],
                "Cantidad": d["Cantidad"],
                "Peso (lb)": float(d["Peso"]),
                "Precio": float(d["Precio"]),
                "Descuento (%)": float(d["Descuento"]),
                "Subtotal": float(d["Subtotal"]),
            })

        fecha_pedido = pedido["Fecha"]
        # Asegurar que sea un objeto date
        if isinstance(fecha_pedido, str):
            from datetime import datetime
            fecha_pedido = datetime.strptime(fecha_pedido, "%Y-%m-%d").date()

        pdf_bytes = generar_factura_pdf(
            id_pedido=factura_sel,
            fecha=fecha_pedido,
            cliente_nombre=cliente_nombre,
            cliente_tel=cliente_tel,
            cliente_dir=cliente_dir,
            metodo_pago=nuevo_pago,
            lineas=lineas_pdf,
            total=float(pedido["Total"]),
            envio=pedido["Envío"],
            cliente_nit=cliente_nit,
        )

        nombre_archivo = cliente_nombre.replace(" ", "")
        st.download_button(
            label="📄 Descargar Factura PDF",
            data=pdf_bytes,
            file_name=f"Factura_{factura_sel}_{nombre_archivo}.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True,
        )
    else:
        st.button(
            "📄 Descargar Factura PDF",
            disabled=True,
            use_container_width=True,
            help="No hay detalle para generar la factura",
        )

# ══════════════════════════════════════════════════════════════════════
# SECCIÓN – MENSAJE DE COBRO PARA COPIAR/PEGAR
# ══════════════════════════════════════════════════════════════════════
st.divider()
render_seccion_mensaje_cobro(
    nombre=cliente_nombre,
    total=float(pedido["Total"]),
    metodo_pago=nuevo_pago,
    key_prefix=f"cons_msg_{factura_sel}",
)

# ── Indicadores visuales de estado ───────────────────────────────────
st.divider()

# Mostrar badges de estado actuales
estado_colors = {
    "Pagado": "🟢",
    "Pendiente de Pago": "🟡",
    "Anulado": "🔴",
}
entrega_icon = "✅" if entregado_actual else "⏳"

st.markdown(
    f"**Estado actual:** {estado_colors.get(estado_actual, '⚪')} {estado_actual} "
    f"&nbsp;|&nbsp; **Entrega:** {entrega_icon} "
    f"{'Entregado' if entregado_actual else 'Pendiente de entrega'}"
)
