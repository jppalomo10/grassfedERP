"""Componente de Streamlit para generar y copiar el mensaje de cobro.

Mantiene `mensajes.py` libre de dependencias de Streamlit. Esta capa arma los
controles (Doña/Don, link de tarjeta) y muestra el texto con botón de copiar.
Cuando el método es "Tarjeta", ofrece generar el link de pago de QPayPro
automáticamente (vía `qpaypro_panel.ClientePanel`); el campo manual queda
siempre como respaldo y tiene prioridad si se llena.
"""
import streamlit as st

from mensajes import generar_mensaje_cobro
from qpaypro_panel import ClientePanel


def _link_generado_vigente(guardado, total, id_pedido):
    """Devuelve la URL cacheada solo si sigue correspondiendo al pedido actual.

    Si el total o el pedido cambiaron después de generar el link, el link viejo
    cobraría un monto equivocado: se descarta (devuelve None).
    """
    if not guardado:
        return None
    if guardado.get("total") != round(float(total), 2):
        return None
    if guardado.get("id_pedido") != id_pedido:
        return None
    return guardado.get("url")


def _generar_link(nombre, total, id_pedido):
    """Genera el link con el cliente del panel (cacheado en la sesión).

    Devuelve la URL o None (mostrando el error en pantalla).
    """
    config = st.secrets.get("qpaypro_panel")
    if not config:
        st.warning(
            "Falta la sección [qpaypro_panel] en los secrets (email, password, "
            "template_id). Configúrala para generar links automáticamente."
        )
        return None

    if "_qpaypro_cliente_panel" not in st.session_state:
        st.session_state["_qpaypro_cliente_panel"] = ClientePanel(dict(config))

    with st.spinner("Generando link de pago en QPayPro..."):
        resultado = st.session_state["_qpaypro_cliente_panel"].crear_link(
            nombre=nombre, total=float(total), id_pedido=id_pedido,
        )
    if not resultado.ok:
        st.error(f"No se pudo generar el link: {resultado.error}")
        return None
    return resultado.url


def render_seccion_mensaje_cobro(nombre, total, metodo_pago, key_prefix, id_pedido=None):
    """Dibuja la sección "Mensaje de cobro" dentro de un expander.

    Args:
        nombre: Nombre del cliente (puede venir vacío).
        total: Total del pedido (float/Decimal).
        metodo_pago: "Efectivo", "Transferencia", "Tarjeta" o "".
        key_prefix: Prefijo único para las keys de los widgets de la página.
        id_pedido: Número del pedido para la descripción del link ("NOMBRE # PEDIDO").
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
                    placeholder="Se genera con el botón, o pega uno manual",
                )

        if metodo_pago == "Tarjeta":
            clave_gen = f"{key_prefix}_link_gen"
            vigente = _link_generado_vigente(
                st.session_state.get(clave_gen), total, id_pedido,
            )
            if st.session_state.get(clave_gen) and vigente is None:
                # El total o el pedido cambiaron: el link cacheado quedó viejo.
                del st.session_state[clave_gen]

            if st.button(
                "🔗 Generar link de pago",
                key=f"{key_prefix}_btn_link",
                help="Crea el link en QPayPro (con facturación electrónica) "
                     "y lo inserta en el mensaje.",
            ):
                url = _generar_link(nombre, total, id_pedido)
                if url:
                    st.session_state[clave_gen] = {
                        "url": url,
                        "total": round(float(total), 2),
                        "id_pedido": id_pedido,
                    }
                    vigente = url

            if vigente:
                st.success(f"Link generado: {vigente}")
                if not link.strip():
                    link = vigente

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
