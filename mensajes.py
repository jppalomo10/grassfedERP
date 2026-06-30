"""Generación del mensaje de cobro para copiar y pegar (WhatsApp).

Función pura, sin dependencias de Streamlit ni de la base de datos, para que sea
fácilmente reutilizable desde las páginas y testeable de forma aislada.
"""

# Datos de la cuenta para recibir transferencias.
DATOS_BANCARIOS = {
    "banco": "Banrural",
    "tipo": "Cuenta monetaria",
    "numero": "3256009530",
    "nombre": "PRODECA",
}

_PETICION_COMPROBANTE = (
    "Le agradecemos nos pueda compartir el comprobante de pago. ¡Gracias!"
)


def _bloque_transferencia() -> str:
    return (
        "Le adjunto el detalle de su pedido y los datos de la cuenta para realizar "
        "su pago:\n\n"
        f"Banco: {DATOS_BANCARIOS['banco']}\n"
        f"{DATOS_BANCARIOS['tipo']}: {DATOS_BANCARIOS['numero']}\n"
        f"A nombre de: {DATOS_BANCARIOS['nombre']}\n\n"
        f"{_PETICION_COMPROBANTE}"
    )


def _bloque_tarjeta(link_tarjeta: str) -> str:
    if link_tarjeta.strip():
        return (
            "Le adjunto el detalle de su pedido y el link para realizar su pago "
            "con tarjeta:\n\n"
            f"{link_tarjeta.strip()}\n\n"
            f"{_PETICION_COMPROBANTE}"
        )
    return (
        "Le adjunto el detalle de su pedido. Para el pago con tarjeta le "
        "enviaremos el link de pago en breve.\n\n"
        f"{_PETICION_COMPROBANTE}"
    )


def _bloque_efectivo() -> str:
    return "Le adjunto el detalle de su pedido. ¡Muchas gracias!"


def generar_mensaje_cobro(
    nombre: str,
    total: float,
    metodo_pago: str,
    titulo: str = "Doña",
    link_tarjeta: str = "",
) -> str:
    """Arma el mensaje de cobro listo para copiar y pegar.

    Args:
        nombre: Nombre del cliente.
        total: Total del pedido en quetzales.
        metodo_pago: "Transferencia", "Tarjeta" o "Efectivo".
        titulo: Tratamiento del cliente ("Doña" / "Don").
        link_tarjeta: Link de pago para tarjeta (opcional).

    Returns:
        El mensaje completo como una sola cadena de texto.
    """
    saludo = (
        f"Buen día {titulo} {nombre}, el total de su pedido es de "
        f"GTQ {total:,.2f}."
    )

    if metodo_pago == "Transferencia":
        bloque = _bloque_transferencia()
    elif metodo_pago == "Tarjeta":
        bloque = _bloque_tarjeta(link_tarjeta)
    else:  # Efectivo o cualquier otro
        bloque = _bloque_efectivo()

    return f"{saludo} {bloque}"
