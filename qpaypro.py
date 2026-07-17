"""Cliente de QPayPro para generar links de pago alojados (App Checkout).

Sin dependencias de Streamlit ni de la base de datos, para mantener la lógica
testeable de forma aislada (igual que `mensajes.py`).

Flujo: se arma el cuerpo de la petición con `construir_payload` y se envía a
`register_transaction_store`; QPayPro devuelve un token con el que se construye
el link final `{base}/checkout/store?token=...` que se envía por WhatsApp.

Ver diseño: docs/superpowers/specs/2026-07-03-qpaypro-link-pago-design.md
"""
import json
import re
from dataclasses import dataclass

import requests

# Nombre de producto por defecto (replica lo que el operador usa hoy en el panel).
NOMBRE_PRODUCTO_DEFECTO = "Caja surtida de carne de pastoreo"

# Host base según entorno. El token se crea y el link se sirve desde el mismo host.
BASES = {
    "sandbox": "https://sandboxpayments.qpaypro.com",
    "produccion": "https://payments.qpaypro.com",
}

# Tiempo máximo de espera (segundos) para la llamada HTTP a QPayPro.
_TIMEOUT = 20


@dataclass
class ResultadoLink:
    """Resultado de intentar generar un link de pago.

    `ok=True` trae `url`; `ok=False` trae `error` con un mensaje legible.
    Nunca se propaga una excepción hacia la UI.
    """
    ok: bool
    url: str | None = None
    error: str | None = None


def _base_para(config) -> str:
    entorno = (config.get("entorno") or "sandbox").strip().lower()
    return BASES.get(entorno, BASES["sandbox"])


def _partir_nombre(nombre: str) -> tuple[str, str]:
    """Separa el nombre en (first_name, last_name).

    La API exige `x_last_name`; si no hay apellido se usa un relleno.
    """
    partes = nombre.strip().split()
    if not partes:
        return ("Cliente", "-")
    if len(partes) == 1:
        return (partes[0], "-")
    return (partes[0], " ".join(partes[1:]))


def construir_payload(nombre, telefono, total, id_pedido=None, correo="", *, config) -> dict:
    """Arma el cuerpo (dict) de la petición a `register_transaction_store`.

    Función pura: no hace red. Mapea los datos del pedido a los campos de QPayPro.
    """
    first_name, last_name = _partir_nombre(nombre)
    telefono_digitos = re.sub(r"\D", "", telefono or "")
    monto = f"{float(total):.2f}"
    email = (correo or "").strip() or config.get("email_relleno", "")
    nombre_producto = config.get("nombre_producto") or NOMBRE_PRODUCTO_DEFECTO
    http_origin = config.get("http_origin") or "grassfedgt.com"
    url_retorno = config.get("url_retorno") or "https://grassfedgt.com"

    nombre_limpio = nombre.strip()
    if id_pedido is not None:
        descripcion = f"{nombre_limpio} # {id_pedido}"
        invoice_num = str(id_pedido)
    else:
        descripcion = nombre_limpio
        invoice_num = ""

    # Posiciones confirmadas contra sandbox (la doc es engañosa):
    # [nombre, id, imagen, cantidad, precio_unitario, ¿flag?]
    # El checkout toma el precio de la posición 4; si el monto va en la 1,
    # la página muestra Q1.00 y cobraría mal.
    products = json.dumps([[nombre_producto, "1", "", "1", monto, "1"]])

    return {
        "x_login": config["x_login"],
        "x_api_key": config["x_api_key"],
        "x_amount": monto,
        "x_currency_code": "GTQ",
        "x_first_name": first_name,
        "x_last_name": last_name,
        "x_phone": telefono_digitos,
        "x_email": email,
        "x_description": descripcion,
        "x_invoice_num": invoice_num,
        "products": products,
        "taxes": "0.00",
        "store_type": "hostedpage",
        "x_discount": "0",
        # Requeridos por la API (aunque la doc no los marque con *). Datos del
        # comercio / retorno; en página alojada el cliente ingresa los suyos.
        "http_origin": http_origin,
        "origen": "PLUGIN",
        "x_url_success": url_retorno,
        "x_url_error": url_retorno,
        "x_url_cancel": url_retorno,
        "x_company": "C/F",
        "x_address": config.get("direccion_comercio") or "Ciudad",
        "x_city": "Guatemala",
        "x_state": "0",
        "x_zip": "01001",
    }


def _extraer_token(data):
    """Busca el token en la respuesta de QPayPro.

    La forma exacta no está documentada; se revisa el nivel superior y algunos
    contenedores comunes. Se ajustará tras la verificación en sandbox.
    """
    if not isinstance(data, dict):
        return None
    if data.get("token"):
        return data["token"]
    for clave in ("responseObject", "data", "response"):
        contenedor = data.get(clave)
        if isinstance(contenedor, dict) and contenedor.get("token"):
            return contenedor["token"]
    return None


def generar_link_pago(nombre, telefono, total, id_pedido=None, correo="", *, config) -> ResultadoLink:
    """Genera un link de pago alojado en QPayPro.

    Devuelve `ResultadoLink`; nunca lanza excepción hacia la UI. Errores de red,
    de estado HTTP o de respuesta sin token se traducen en `ok=False`.
    """
    base = _base_para(config)
    payload = construir_payload(
        nombre=nombre, telefono=telefono, total=total,
        id_pedido=id_pedido, correo=correo, config=config,
    )

    try:
        resp = requests.post(
            f"{base}/checkout/register_transaction_store",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=_TIMEOUT,
        )
    except requests.RequestException as e:
        return ResultadoLink(ok=False, error=f"No se pudo contactar a QPayPro: {e}")

    if resp.status_code // 100 != 2:
        return ResultadoLink(
            ok=False, error=f"QPayPro respondió con código {resp.status_code}.",
        )

    try:
        data = resp.json()
    except ValueError as e:
        return ResultadoLink(ok=False, error=f"Respuesta no válida de QPayPro: {e}")

    token = _extraer_token(data)
    if not token:
        return ResultadoLink(
            ok=False, error="QPayPro no devolvió un token en la respuesta.",
        )

    return ResultadoLink(ok=True, url=f"{base}/checkout/store?token={token}")
