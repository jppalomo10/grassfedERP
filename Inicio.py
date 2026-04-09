# Importaciones
import streamlit as st
import pandas as pd
from db import run_query
from auth import check_login, role_badge, get_role
from pdf_utils import generar_rutas_envio_pdf, generar_factura_pdf, costos_envio

st.set_page_config(
    page_title="Sistema ERP",
    page_icon="🏠",
    layout="wide"
)

# Autenticación
if not check_login():
    st.stop()

st.sidebar.markdown(f"**{st.session_state.user}** · {role_badge()}")
if st.sidebar.button("Cerrar Sesión"):
    for key in ["authenticated", "user", "role"]:
        st.session_state.pop(key, None)
    st.rerun()

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

st.divider()

# ══════════════════════════════════════════════════════════════════════
# RESUMEN DE PEDIDOS PENDIENTES
# ══════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=120)
def get_pendientes_pago():
    rows = run_query("""
        SELECT p."ID_Pedido", p."Fecha", c."Nombre" AS "Cliente",
               p."Total", p."Pago"
        FROM "Pedidos" p
        JOIN "Clientes" c ON p."Cliente" = c."Teléfono"
        WHERE p."Estado" = 'Pendiente de Pago'
        AND p."Estado" != 'Anulado'
        ORDER BY p."Fecha" DESC
    """)
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["ID_Pedido", "Fecha", "Cliente", "Total", "Pago"]
    )

@st.cache_data(ttl=120)
def get_pendientes_envio():
    rows = run_query("""
        SELECT p."ID_Pedido", p."Fecha", c."Nombre" AS "Cliente",
               p."Total", p."Envío"
        FROM "Pedidos" p
        JOIN "Clientes" c ON p."Cliente" = c."Teléfono"
        WHERE p."Entregado" = false
        AND p."Estado" != 'Anulado'
        ORDER BY p."Fecha" DESC
    """)
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["ID_Pedido", "Fecha", "Cliente", "Total", "Envío"]
    )

@st.cache_data(ttl=120)
def get_rutas_envio():
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


def get_facturas_pendientes_envio():
    """Obtiene todos los pedidos pendientes de envío con datos completos para generar facturas."""
    rows = run_query("""
        SELECT p."ID_Pedido", p."Fecha", p."Total", p."Pago", p."Envío",
               c."Nombre", c."Teléfono", c."Dirección",
               COALESCE(c."NIT", 'C/F') AS "NIT"
        FROM "Pedidos" p
        JOIN "Clientes" c ON p."Cliente" = c."Teléfono"
        WHERE p."Entregado" = false
          AND p."Estado" != 'Anulado'
        ORDER BY p."ID_Pedido" DESC
    """)
    return rows if rows else []


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


def generar_zip_facturas():
    """Genera un ZIP con todas las facturas de pedidos pendientes de envío."""
    import zipfile
    from io import BytesIO

    pedidos = get_facturas_pendientes_envio()
    if not pedidos:
        return None

    zip_buf = BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for ped in pedidos:
            detalle = get_detalle_pedido(ped["ID_Pedido"])
            if not detalle:
                continue

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

            fecha_pedido = ped["Fecha"]
            if isinstance(fecha_pedido, str):
                from datetime import datetime
                fecha_pedido = datetime.strptime(fecha_pedido, "%Y-%m-%d").date()

            pdf_bytes = generar_factura_pdf(
                id_pedido=ped["ID_Pedido"],
                fecha=fecha_pedido,
                cliente_nombre=ped["Nombre"],
                cliente_tel=ped["Teléfono"],
                cliente_dir=ped["Dirección"],
                metodo_pago=ped["Pago"],
                lineas=lineas_pdf,
                total=float(ped["Total"]),
                envio=ped["Envío"],
                cliente_nit=ped["NIT"],
            )

            nombre_archivo = ped["Nombre"].replace(" ", "")
            zf.writestr(
                f"Factura_{ped['ID_Pedido']}_{nombre_archivo}.pdf",
                pdf_bytes.read(),
            )

    zip_buf.seek(0)
    return zip_buf


df_pago = get_pendientes_pago()
df_envio = get_pendientes_envio()

col_pago, col_envio = st.columns(2)

with col_pago:
    st.subheader("💳 Pendientes de Pago")
    if df_pago.empty:
        st.success("No hay pedidos pendientes de pago.")
    else:
        st.caption(f"{len(df_pago)} pedido(s)")
        st.dataframe(
            df_pago,
            use_container_width=True,
            hide_index=True,
            column_config={
                "ID_Pedido": st.column_config.NumberColumn("# Factura"),
                "Fecha": st.column_config.DateColumn("Fecha"),
                "Total": st.column_config.NumberColumn("Total", format="Q%.2f"),
            },
        )

with col_envio:
    st.subheader("📦 Pendientes de Envío")
    if df_envio.empty:
        st.success("No hay pedidos pendientes de envío.")
    else:
        st.caption(f"{len(df_envio)} pedido(s)")
        st.dataframe(
            df_envio,
            use_container_width=True,
            hide_index=True,
            column_config={
                "ID_Pedido": st.column_config.NumberColumn("# Factura"),
                "Fecha": st.column_config.DateColumn("Fecha"),
                "Total": st.column_config.NumberColumn("Total", format="Q%.2f"),
            },
        )

    # Botón para descargar hoja de rutas
    rutas = get_rutas_envio()
    if rutas:
        st.download_button(
            label="🚚 Descargar Rutas de Envío (PDF)",
            data=generar_rutas_envio_pdf(rutas),
            file_name="Rutas_Envio.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True,
        )

# ══════════════════════════════════════════════════════════════════════
# DESCARGAR TODAS LAS FACTURAS PENDIENTES DE ENVÍO
# ══════════════════════════════════════════════════════════════════════
st.divider()

if not df_envio.empty:
    if st.button("📄 Generar Facturas Pendientes de Envío (ZIP)", type="primary", use_container_width=True):
        with st.spinner("Generando facturas..."):
            zip_data = generar_zip_facturas()
        if zip_data:
            st.download_button(
                label="⬇️ Descargar ZIP de Facturas",
                data=zip_data,
                file_name="Facturas_Pendientes_Envio.zip",
                mime="application/zip",
                use_container_width=True,
            )
        else:
            st.warning("No se encontraron facturas con detalle para generar.")