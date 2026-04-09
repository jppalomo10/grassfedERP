# Importaciones
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
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
# QUERIES
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


@st.cache_data(ttl=300)
def get_ventas_diarias_mes():
    """Ventas del mes en curso agrupadas por día: total Q y lbs."""
    rows = run_query("""
        SELECT
            p."Fecha",
            SUM(p."Total")          AS "Ventas_Q",
            COALESCE(SUM(d."Peso"), 0) AS "Ventas_Lbs"
        FROM "Pedidos" p
        LEFT JOIN "DetallePedido" d ON d."ID_Pedido" = p."ID_Pedido"
        WHERE DATE_TRUNC('month', p."Fecha") = DATE_TRUNC('month', CURRENT_DATE)
          AND p."Estado" != 'Anulado'
        GROUP BY p."Fecha"
        ORDER BY p."Fecha"
    """)
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["Fecha", "Ventas_Q", "Ventas_Lbs"]
    )


@st.cache_data(ttl=300)
def get_resumen_mes():
    """KPIs del mes en curso."""
    row = run_query("""
        SELECT
            COUNT(DISTINCT p."ID_Pedido")    AS num_pedidos,
            COALESCE(SUM(p."Total"), 0)      AS total_q,
            COALESCE(SUM(d."Peso"), 0)       AS total_lbs,
            COALESCE(AVG(p."Total"), 0)      AS ticket_promedio
        FROM "Pedidos" p
        LEFT JOIN "DetallePedido" d ON d."ID_Pedido" = p."ID_Pedido"
        WHERE DATE_TRUNC('month', p."Fecha") = DATE_TRUNC('month', CURRENT_DATE)
          AND p."Estado" != 'Anulado'
    """, fetch="one")
    return row


@st.cache_data(ttl=300)
def get_ventas_por_producto_mes():
    """Ventas del mes agrupadas por producto."""
    rows = run_query("""
        SELECT
            pr."Producto",
            SUM(dp."Subtotal") AS "Ventas_Q",
            SUM(dp."Peso")     AS "Ventas_Lbs",
            SUM(dp."Cantidad") AS "Unidades"
        FROM "DetallePedido" dp
        JOIN "Pedidos" p    ON dp."ID_Pedido" = p."ID_Pedido"
        JOIN "Productos" pr ON dp."SKU"       = pr."SKU"
        WHERE DATE_TRUNC('month', p."Fecha") = DATE_TRUNC('month', CURRENT_DATE)
          AND p."Estado" != 'Anulado'
        GROUP BY pr."Producto"
        ORDER BY "Ventas_Q" DESC
    """)
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["Producto", "Ventas_Q", "Ventas_Lbs", "Unidades"]
    )


@st.cache_data(ttl=300)
def get_ventas_por_pago_mes():
    """Ventas del mes agrupadas por método de pago."""
    rows = run_query("""
        SELECT
            p."Pago",
            COUNT(*)           AS "Pedidos",
            SUM(p."Total")     AS "Total_Q"
        FROM "Pedidos" p
        WHERE DATE_TRUNC('month', p."Fecha") = DATE_TRUNC('month', CURRENT_DATE)
          AND p."Estado" != 'Anulado'
        GROUP BY p."Pago"
        ORDER BY "Total_Q" DESC
    """)
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["Pago", "Pedidos", "Total_Q"]
    )


@st.cache_data(ttl=300)
def get_top_clientes_mes():
    """Top clientes del mes por monto comprado."""
    rows = run_query("""
        SELECT
            c."Nombre",
            COUNT(DISTINCT p."ID_Pedido") AS "Pedidos",
            SUM(p."Total")                AS "Total_Q"
        FROM "Pedidos" p
        JOIN "Clientes" c ON p."Cliente" = c."Teléfono"
        WHERE DATE_TRUNC('month', p."Fecha") = DATE_TRUNC('month', CURRENT_DATE)
          AND p."Estado" != 'Anulado'
        GROUP BY c."Nombre"
        ORDER BY "Total_Q" DESC
        LIMIT 10
    """)
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["Nombre", "Pedidos", "Total_Q"]
    )


# ══════════════════════════════════════════════════════════════════════
# TABS PRINCIPALES
# ══════════════════════════════════════════════════════════════════════

tab_pedidos, tab_reporte = st.tabs(["📋 Pedidos Pendientes", "📊 Reporte del Mes"])

# ── TAB 1: PEDIDOS PENDIENTES ─────────────────────────────────────────
with tab_pedidos:
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


# ── TAB 2: REPORTE DEL MES ────────────────────────────────────────────
with tab_reporte:
    from datetime import date
    mes_actual = date.today().strftime("%B %Y")
    st.subheader(f"📊 Reporte de Ventas — {mes_actual}")

    resumen = get_resumen_mes()

    # KPI cards
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("Pedidos del mes", int(resumen["num_pedidos"]) if resumen else 0)
    with k2:
        total_q = float(resumen["total_q"]) if resumen else 0
        st.metric("Ventas totales", f"Q {total_q:,.2f}")
    with k3:
        total_lbs = float(resumen["total_lbs"]) if resumen else 0
        st.metric("Peso vendido", f"{total_lbs:,.1f} lbs")
    with k4:
        ticket = float(resumen["ticket_promedio"]) if resumen else 0
        st.metric("Ticket promedio", f"Q {ticket:,.2f}")

    st.divider()

    # ── Gráfica doble eje: Q y lbs por día ───────────────────────────
    st.markdown("#### Ventas diarias del mes")
    df_diario = get_ventas_diarias_mes()

    if df_diario.empty:
        st.info("Aún no hay ventas registradas este mes.")
    else:
        df_diario["Ventas_Q"]   = df_diario["Ventas_Q"].astype(float)
        df_diario["Ventas_Lbs"] = df_diario["Ventas_Lbs"].astype(float)
        df_diario["Fecha_str"]  = pd.to_datetime(df_diario["Fecha"]).dt.strftime("%d/%m")

        fig = go.Figure()

        fig.add_trace(go.Bar(
            x=df_diario["Fecha_str"],
            y=df_diario["Ventas_Q"],
            name="Ventas (Q)",
            marker_color="#2e7d32",
            yaxis="y1",
        ))

        fig.add_trace(go.Scatter(
            x=df_diario["Fecha_str"],
            y=df_diario["Ventas_Lbs"],
            name="Peso (lbs)",
            mode="lines+markers",
            marker=dict(color="#f57c00", size=7),
            line=dict(color="#f57c00", width=2),
            yaxis="y2",
        ))

        fig.update_layout(
            yaxis=dict(
                title=dict(text="Quetzales (Q)", font=dict(color="#2e7d32")),
                tickfont=dict(color="#2e7d32"),
                tickprefix="Q ",
            ),
            yaxis2=dict(
                title=dict(text="Peso (lbs)", font=dict(color="#f57c00")),
                tickfont=dict(color="#f57c00"),
                overlaying="y",
                side="right",
                ticksuffix=" lbs",
            ),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hovermode="x unified",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=10, r=10, t=30, b=10),
            height=380,
        )

        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Tablas de detalle ─────────────────────────────────────────────
    col_prod, col_cliente = st.columns(2)

    with col_prod:
        st.markdown("#### Ventas por producto")
        df_prod = get_ventas_por_producto_mes()
        if df_prod.empty:
            st.info("Sin datos.")
        else:
            df_prod["Ventas_Q"]   = df_prod["Ventas_Q"].astype(float)
            df_prod["Ventas_Lbs"] = df_prod["Ventas_Lbs"].astype(float)
            st.dataframe(
                df_prod,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Producto":   st.column_config.TextColumn("Producto"),
                    "Ventas_Q":   st.column_config.NumberColumn("Ventas (Q)", format="Q%.2f"),
                    "Ventas_Lbs": st.column_config.NumberColumn("Peso (lbs)", format="%.1f lbs"),
                    "Unidades":   st.column_config.NumberColumn("Unidades"),
                },
            )

    with col_cliente:
        st.markdown("#### Top 10 clientes del mes")
        df_cli = get_top_clientes_mes()
        if df_cli.empty:
            st.info("Sin datos.")
        else:
            df_cli["Total_Q"] = df_cli["Total_Q"].astype(float)
            st.dataframe(
                df_cli,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Nombre":   st.column_config.TextColumn("Cliente"),
                    "Pedidos":  st.column_config.NumberColumn("Pedidos"),
                    "Total_Q":  st.column_config.NumberColumn("Total (Q)", format="Q%.2f"),
                },
            )

    st.divider()

    # ── Método de pago ────────────────────────────────────────────────
    st.markdown("#### Desglose por método de pago")
    df_pago_metodo = get_ventas_por_pago_mes()
    if df_pago_metodo.empty:
        st.info("Sin datos.")
    else:
        df_pago_metodo["Total_Q"] = df_pago_metodo["Total_Q"].astype(float)

        col_pie, col_tabla_pago = st.columns([1, 1])
        with col_pie:
            fig_pie = go.Figure(go.Pie(
                labels=df_pago_metodo["Pago"],
                values=df_pago_metodo["Total_Q"],
                hole=0.4,
                marker=dict(colors=["#2e7d32", "#f57c00", "#1565c0", "#6a1b9a"]),
                textinfo="label+percent",
            ))
            fig_pie.update_layout(
                showlegend=False,
                margin=dict(l=10, r=10, t=10, b=10),
                height=260,
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        with col_tabla_pago:
            st.dataframe(
                df_pago_metodo,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Pago":     st.column_config.TextColumn("Método"),
                    "Pedidos":  st.column_config.NumberColumn("Pedidos"),
                    "Total_Q":  st.column_config.NumberColumn("Total (Q)", format="Q%.2f"),
                },
            )
