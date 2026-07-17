"""Cliente de la API interna del panel de QPayPro (módulo "Links de Pago").

Crea links de pago idénticos a los que el operador crea a mano en el panel
(app.qpaypro.com): mismo formato de URL (`/checkout/{código}/{id}`), misma
plantilla y con facturación electrónica FEL (`infile: 1`).

⚠️ Es una API interna, no documentada: puede cambiar sin aviso. Por eso la UI
mantiene siempre el campo manual como respaldo. La autenticación es por sesión
del panel (email/password en secrets), no por llaves de comercio; la sesión se
cachea en la instancia y se renueva sola cuando expira (HTTP 401/419).

Sin dependencias de Streamlit ni de la base de datos, igual que `qpaypro.py`.
Ver diseño: docs/superpowers/specs/2026-07-03-qpaypro-link-pago-design.md
"""
from urllib.parse import unquote

import requests

from qpaypro import NOMBRE_PRODUCTO_DEFECTO, ResultadoLink

BASE_PANEL = "https://app.qpaypro.com"

# Tiempo máximo de espera (segundos) por llamada HTTP.
_TIMEOUT = 30

_HEADERS_BASE = {
    "accept": "application/json, text/plain, */*",
    "origin": BASE_PANEL,
    "referer": f"{BASE_PANEL}/payment-links",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
    ),
    "x-requested-with": "XMLHttpRequest",
}


def construir_payload_link(nombre, total, id_pedido=None, *, config) -> dict:
    """Arma el cuerpo del POST a /api/payment-links.

    Replica la estructura que el operador usa en el panel:
    nombre de producto fijo, descripción "NOMBRE # PEDIDO", GTQ, FEL activa,
    precio y cantidad no editables por el cliente.
    """
    nombre_limpio = (nombre or "").strip()
    if id_pedido is not None:
        descripcion = f"{nombre_limpio} # {id_pedido}"
    else:
        descripcion = nombre_limpio

    return {
        "name": config.get("nombre_producto") or NOMBRE_PRODUCTO_DEFECTO,
        "description": descripcion,
        "price": round(float(total), 2),
        "currency": "GTQ",
        "price_editable": False,
        "quantity_edit": False,
        "quantity": 1,
        "enabled_shipping": False,
        "shipping_cost": 0,
        "enabled_visa_cuota": False,
        "installments": [],
        "link_pago_venc": False,
        "link_pago_venc_fecha": None,
        "redirect": False,
        "redirect_link": None,
        "language": "es",
        "template": str(config.get("template_id", "")),
        "status": "active",
        "success_url": None,
        "infile": 1 if config.get("fel", True) else 0,
        "custom_fields": [],
    }


class ClientePanel:
    """Sesión autenticada contra el panel + creación de links de pago.

    Cachear la instancia (p. ej. en `st.session_state`) evita un login por
    cada link; si la sesión del panel expira, se renueva sola.
    """

    def __init__(self, config):
        self.config = config
        self.sesion = None

    # -- sesión ------------------------------------------------------------

    def _headers_csrf(self) -> dict:
        """Laravel exige el token CSRF (cookie XSRF-TOKEN, URL-decodificada)."""
        token = unquote(self.sesion.cookies.get("XSRF-TOKEN", "") or "")
        return {"x-xsrf-token": token}

    def _login(self):
        """Inicia sesión en el panel. Devuelve None si tuvo éxito o un error."""
        self.sesion = requests.Session()
        self.sesion.headers.update(_HEADERS_BASE)
        try:
            self.sesion.get(f"{BASE_PANEL}/login", timeout=_TIMEOUT)
            resp = self.sesion.post(
                f"{BASE_PANEL}/login",
                json={
                    "email": self.config["email"],
                    "password": self.config["password"],
                    "remember": True,
                },
                headers=self._headers_csrf(),
                timeout=_TIMEOUT,
                allow_redirects=False,
            )
        except requests.RequestException as e:
            self.sesion = None
            return f"No se pudo contactar al panel de QPayPro: {e}"

        if resp.status_code in (200, 302):
            return None
        self.sesion = None
        if resp.status_code == 422:
            return (
                "El panel rechazó las credenciales (email/password de "
                "[qpaypro_panel] en secrets). Verifícalas."
            )
        return f"El login del panel falló con código {resp.status_code}."

    # -- API ---------------------------------------------------------------

    def crear_link(self, nombre, total, id_pedido=None) -> ResultadoLink:
        """Crea un link de pago; nunca lanza excepción hacia la UI.

        Si la sesión expiró (401/419), re-loguea y reintenta una vez.
        """
        payload = construir_payload_link(
            nombre=nombre, total=total, id_pedido=id_pedido, config=self.config,
        )

        for intento in (1, 2):
            if self.sesion is None:
                error = self._login()
                if error:
                    return ResultadoLink(ok=False, error=error)

            try:
                resp = self.sesion.post(
                    f"{BASE_PANEL}/api/payment-links",
                    json=payload,
                    headers=self._headers_csrf(),
                    timeout=_TIMEOUT,
                )
            except requests.RequestException as e:
                self.sesion = None
                return ResultadoLink(
                    ok=False, error=f"No se pudo contactar al panel: {e}",
                )

            if resp.status_code in (401, 419) and intento == 1:
                self.sesion = None  # sesión vencida → re-login y reintento
                continue

            if resp.status_code not in (200, 201):
                return ResultadoLink(
                    ok=False,
                    error=f"El panel respondió con código {resp.status_code}.",
                )

            try:
                data = resp.json()
            except ValueError as e:
                return ResultadoLink(
                    ok=False, error=f"Respuesta no válida del panel: {e}",
                )

            url = data.get("url") or (data.get("link") or {}).get("url")
            if not url:
                return ResultadoLink(
                    ok=False, error="El panel no devolvió la URL del link.",
                )
            return ResultadoLink(ok=True, url=url)

        return ResultadoLink(ok=False, error="La sesión del panel no se pudo renovar.")
