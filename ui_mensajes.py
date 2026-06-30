"""Componente de Streamlit para generar y copiar el mensaje de cobro.

Mantiene `mensajes.py` libre de dependencias de Streamlit. Esta capa solo arma
los controles (Doña/Don, link de tarjeta) y muestra el texto con botón de copiar.
"""
import streamlit as st

from mensajes import generar_mensaje_cobro


def render_seccion_mensaje_cobro(nombre, total, metodo_pago, key_prefix):
    """Dibuja la sección "Mensaje de cobro" dentro de un expander.

    Args:
        nombre: Nombre del cliente (puede venir vacío).
        total: Total del pedido (float/Decimal).
        metodo_pago: "Efectivo", "Transferencia", "Tarjeta" o "".
        key_prefix: Prefijo único para las keys de los widgets de la página.
    """
    with st.expander("📩 Mensaje de cobro (copiar y pegar)", expanded=False):
        if not nombre:
            st.info("Selecciona un cliente para generar el mensaje.")
            return
        if not metodo_pago:
            st.info("Selecciona el método de pago para generar el mensaje.")
            return

        col_titulo, col_link = st.columns(2)
        with col_titulo:
            titulo = st.radio(
                "Tratamiento",
                ["Doña", "Don"],
                horizontal=True,
                key=f"{key_prefix}_titulo",
            )

        link = ""
        with col_link:
            if metodo_pago == "Tarjeta":
                link = st.text_input(
                    "Link de pago (tarjeta)",
                    key=f"{key_prefix}_link",
                    placeholder="Pega aquí el link de pago (opcional)",
                )

        mensaje = generar_mensaje_cobro(
            nombre=nombre,
            total=float(total),
            metodo_pago=metodo_pago,
            titulo=titulo,
            link_tarjeta=link,
        )
        st.code(mensaje, language=None)
        st.caption(
            "Toca el ícono de copiar (esquina superior derecha del recuadro) "
            "para copiar el mensaje completo."
        )
