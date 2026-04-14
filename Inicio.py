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

@st.cache_data(ttl=120)
def get_reporte_productos(fecha_inicio, fecha_fin):
    query = """
    select
      p."Producto",
      sum(d."Peso") as "Peso",
      round(sum(d."Subtotal"), 2) as "Total (Q)"
    from "DetallePedido" d
    join "Productos" p
      on p."SKU" = d."SKU"
    join "Pedidos" pe
      on pe."ID_Pedido" = d."ID_Pedido"
    where pe."Estado" <> 'Anulado'
      and pe."Fecha" >= %s::date
      and pe."Fecha" <= %s::date
    group by
      p."Producto"
    order by
      round(sum(d."Subtotal")) DESC;
    """
    rows = run_query(query, params=(fecha_inicio, fecha_fin))
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["Producto", "Peso", "Total (Q)"])

@st.cache_data(ttl=120)
def get_reporte_fechas(fecha_inicio, fecha_fin):
    query = """
    select
      "Fecha",
      round(sum("Total"), 2) as "Total (Q)"
    from
      "Pedidos"
    where
      "Estado" != 'Anulado'
      and "Fecha" >= %s::date
      and "Fecha" <= %s::date
    group by
      "Fecha"
    order by
      "Fecha" DESC;
    """
    rows = run_query(query, params=(fecha_inicio, fecha_fin))
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["Fecha", "Total (Q)"])


@st.cache_data(ttl=120)
def get_inventario():
    """Calcula el stock actual por producto.
    Entradas: MovimientosInventario.Debe
    Salidas por transformación: MovimientosInventario.Haber
    Salidas por venta: DetallePedido.Peso (pedidos no anulados)
    """
    rows = run_query("""
        WITH entradas AS (
            SELECT "SKU",
                   COALESCE(SUM("Debe"), 0)  AS debe,
                   COALESCE(SUM("Haber"), 0) AS haber
            FROM "MovimientosInventario"
            GROUP BY "SKU"
        ),
        salidas AS (
            SELECT d."SKU",
                   COALESCE(SUM(d."Peso"), 0) AS peso
            FROM "DetallePedido" d
            JOIN "Pedidos" pe ON pe."ID_Pedido" = d."ID_Pedido"
            WHERE pe."Estado" != 'Anulado'
            GROUP BY d."SKU"
        )
        SELECT p."SKU",
               p."Producto",
               COALESCE(e.debe, 0)  AS "Ingresos (lb)",
               COALESCE(e.haber, 0) AS "Transf. Salida (lb)",
               COALESCE(s.peso, 0)  AS "Ventas (lb)",
               ROUND(CAST(
                   COALESCE(e.debe, 0) - COALESCE(e.haber, 0) - COALESCE(s.peso, 0)
               AS numeric), 2) AS "Stock (lb)"
        FROM "Productos" p
        LEFT JOIN entradas e ON p."SKU" = e."SKU"
        LEFT JOIN salidas  s ON p."SKU" = s."SKU"
        ORDER BY p."Producto"
    """)
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["SKU", "Producto", "Ingresos (lb)", "Transf. Salida (lb)", "Ventas (lb)", "Stock (lb)"]
    )


df_pago = get_pendientes_pago()
df_envio = get_pendientes_envio()

tab1, tab_inv, tab2 = st.tabs(["Pedidos Pendientes", "📦 Inventario", "Reportes de Ventas"])

with tab1:
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

# ══════════════════════════════════════════════════════════════════════
# TAB INVENTARIO
# ══════════════════════════════════════════════════════════════════════
with tab_inv:
    st.subheader("📦 Inventario Actual")

    if st.button("🔄 Actualizar inventario", key="btn_refresh_inv"):
        get_inventario.clear()
        st.rerun()

    df_inv = get_inventario()

    if df_inv.empty:
        st.info("No hay datos de inventario registrados.")
    else:
        # ── Métricas resumen ──────────────────────────────────────────
        total_stock = float(df_inv["Stock (lb)"].sum())
        productos_con_stock = int((df_inv["Stock (lb)"] > 0).sum())
        productos_sin_stock = int((df_inv["Stock (lb)"] <= 0).sum())

        mi1, mi2, mi3 = st.columns(3)
        mi1.metric("Stock total", f"{total_stock:,.2f} lb")
        mi2.metric("Productos con stock", productos_con_stock)
        mi3.metric("Productos sin stock", productos_sin_stock)

        st.divider()

        # ── Tabla de inventario ───────────────────────────────────────
        st.dataframe(
            df_inv,
            use_container_width=True,
            hide_index=True,
            column_config={
                "SKU": st.column_config.TextColumn("SKU"),
                "Producto": st.column_config.TextColumn("Producto"),
                "Ingresos (lb)": st.column_config.NumberColumn(
                    "Ingresos (lb)", format="%.2f"
                ),
                "Transf. Salida (lb)": st.column_config.NumberColumn(
                    "Transf. Salida (lb)", format="%.2f"
                ),
                "Ventas (lb)": st.column_config.NumberColumn(
                    "Ventas (lb)", format="%.2f"
                ),
                "Stock (lb)": st.column_config.NumberColumn(
                    "Stock (lb)", format="%.2f"
                ),
            },
        )

with tab2:
    st.subheader("📊 Reportes de Ventas")
    import datetime

    filtro_fecha = st.selectbox(
        "Filtro de tiempo:",
        ["Esta semana", "Este mes", "Últimos 3 meses", "Personalizado"],
        index=1
    )

    hoy = datetime.datetime.now().date()
    if filtro_fecha == "Esta semana":
        fecha_inicio = hoy - datetime.timedelta(days=hoy.weekday())
        fecha_fin = hoy
    elif filtro_fecha == "Este mes":
        fecha_inicio = hoy.replace(day=1)
        fecha_fin = hoy
    elif filtro_fecha == "Últimos 3 meses":
        fecha_inicio = hoy - datetime.timedelta(days=90)
        fecha_fin = hoy
    else:
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            fecha_inicio = st.date_input("Fecha inicio", value=hoy.replace(day=1), max_value=hoy)
        with col_d2:
            fecha_fin = st.date_input("Fecha fin", value=hoy, max_value=hoy)
        if fecha_inicio > fecha_fin:
            st.error("La fecha de inicio no puede ser mayor que la fecha de fin.")
            st.stop()

    df_prod = get_reporte_productos(fecha_inicio, fecha_fin)
    df_fecha = get_reporte_fechas(fecha_inicio, fecha_fin)

    # ── Métricas resumen ────────────────────────────────────────────────
    total_ventas = float(df_prod["Total (Q)"].sum()) if not df_prod.empty else 0
    total_peso   = float(df_prod["Peso"].sum())      if not df_prod.empty else 0
    num_dias     = len(df_fecha)                     if not df_fecha.empty else 0

    m1, m2, m3 = st.columns(3)
    m1.metric("Total en ventas",      f"Q {total_ventas:,.2f}")
    m2.metric("Peso total vendido",   f"{total_peso:,.2f} lb")
    m3.metric("Días con ventas",      num_dias)

    st.divider()

    # ── Tablas lado a lado ──────────────────────────────────────────────
    col_rep1, col_rep2 = st.columns(2)

    with col_rep1:
        st.markdown("##### Ventas por Producto")
        st.dataframe(
            df_prod,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Peso":      st.column_config.NumberColumn("Peso (lb)",   format="%.3f lb"),
                "Total (Q)": st.column_config.NumberColumn("Total (Q)",   format="Q%,.2f"),
            },
        )

    with col_rep2:
        st.markdown("##### Ventas por Fecha")
        st.dataframe(
            df_fecha,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Fecha":     st.column_config.DateColumn("Fecha"),
                "Total (Q)": st.column_config.NumberColumn("Total (Q)", format="Q%,.2f"),
            },
        )

    # ── Gráfica debajo de las tablas ────────────────────────────────────
    if not df_fecha.empty:
        import plotly.graph_objects as go
        import math

        st.divider()
        st.markdown("##### Tendencia de Ventas")

        df_chart = df_fecha.sort_values("Fecha").copy()
        df_chart["Fecha"] = pd.to_datetime(df_chart["Fecha"])

        max_val = float(df_chart["Total (Q)"].max())
        if max_val > 0:
            exp = math.floor(math.log10(max_val))
            nice_max = 1.5 * (10 ** exp)
        else:
            nice_max = 1

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_chart["Fecha"],
            y=df_chart["Total (Q)"],
            mode="lines+markers",
            line=dict(width=2),
            marker=dict(size=7),
            hovertemplate="<b>%{x|%d %b %Y}</b><br>Q %{y:,.2f}<extra></extra>",
        ))
        fig.update_layout(
            height=320,
            margin=dict(t=10, b=10, l=10, r=10),
            xaxis=dict(
                tickformat="%d %b",
                dtick="D1",
                tickangle=-30,
                title=None,
            ),
            yaxis=dict(
                range=[0, nice_max],
                tickformat=".3s",
                title="Total (Q)",
            ),
        )
        st.plotly_chart(fig, use_container_width=True)