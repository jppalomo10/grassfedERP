"""Pruebas del cliente de la API interna del panel de QPayPro (payment-links).

Genera links idénticos a los del módulo "Links de Pago" del panel, con FEL
(`infile`). La autenticación es por sesión (login con email/password del panel).
Todo el HTTP se mockea; la única frontera de I/O es `requests.Session`.
"""
import pytest

import qpaypro_panel
from qpaypro_panel import ClientePanel, construir_payload_link


CONFIG = {
    "email": "operador@example.com",
    "password": "secreta",
    "template_id": "1310",
}


# --------------------------------------------------------------------------
# construir_payload_link (función pura) — estructura que usa el operador:
#   Nombre: Caja surtida de carne de pastoreo / Descripción: NOMBRE # PEDIDO
#   Moneda: GTQ / FEL: activa
# --------------------------------------------------------------------------

def test_payload_replica_la_estructura_del_operador():
    p = construir_payload_link(
        nombre="MARIA LOPEZ", total=400.93, id_pedido=450, config=CONFIG,
    )
    assert p["name"] == "Caja surtida de carne de pastoreo"
    assert p["description"] == "MARIA LOPEZ # 450"
    assert p["price"] == 400.93
    assert p["currency"] == "GTQ"
    assert p["infile"] == 1              # FEL activa
    assert p["template"] == "1310"
    assert p["status"] == "active"
    assert p["price_editable"] is False  # cliente no puede cambiar el monto
    assert p["quantity_edit"] is False
    assert p["quantity"] == 1
    assert p["language"] == "es"


def test_payload_descripcion_sin_pedido_no_lleva_numeral():
    p = construir_payload_link(nombre="ANA", total=10.0, config=CONFIG)
    assert p["description"] == "ANA"
    assert "#" not in p["description"]


def test_payload_fel_desactivable_por_config():
    cfg = {**CONFIG, "fel": False}
    p = construir_payload_link(nombre="ANA", total=10.0, id_pedido=1, config=cfg)
    assert p["infile"] == 0


def test_payload_nombre_producto_configurable():
    cfg = {**CONFIG, "nombre_producto": "Media caja surtida"}
    p = construir_payload_link(nombre="ANA", total=10.0, id_pedido=1, config=cfg)
    assert p["name"] == "Media caja surtida"


def test_payload_redondea_precio_a_dos_decimales():
    p = construir_payload_link(nombre="ANA", total=100.005, id_pedido=1, config=CONFIG)
    assert p["price"] == 100.0  # round() bancario de Python sobre 2 decimales


# --------------------------------------------------------------------------
# ClientePanel (login + crear_link, con requests.Session mockeado)
# --------------------------------------------------------------------------

class _FakeResp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        if self._payload is None:
            raise ValueError("sin json")
        return self._payload


class _FakeSession:
    """Enruta get/post por URL y consume respuestas en orden por ruta."""

    def __init__(self, respuestas):
        self.respuestas = respuestas  # {"POST /login": [resp, ...], ...}
        self.llamadas = []            # [("POST", url, json), ...]
        self.headers = {}
        self.cookies = {"XSRF-TOKEN": "tok%3D"}

    def _ruta(self, metodo, url):
        sufijo = "/api/payment-links" if "/api/payment-links" in url else "/login"
        return f"{metodo} {sufijo}"

    def _responder(self, metodo, url, json=None):
        self.llamadas.append((metodo, url, json))
        cola = self.respuestas.get(self._ruta(metodo, url))
        if not cola:
            raise AssertionError(f"llamada inesperada: {metodo} {url}")
        return cola.pop(0)

    def get(self, url, **kw):
        return self._responder("GET", url)

    def post(self, url, json=None, **kw):
        return self._responder("POST", url, json)


@pytest.fixture
def fake_session(monkeypatch):
    """Inyecta una fábrica de _FakeSession en qpaypro_panel.requests.Session."""
    creadas = []

    def instalar(respuestas):
        def fabrica():
            # Cada login crea una sesión nueva; todas comparten las colas.
            s = _FakeSession(respuestas)
            creadas.append(s)
            return s
        monkeypatch.setattr(qpaypro_panel.requests, "Session", fabrica)
        return creadas

    return instalar


_URL_CREADA = "https://payments.qpaypro.com/checkout/dK6w2o6u42yB3688/451678"


def _respuestas_ok(extra_api=None):
    api = extra_api or [_FakeResp(201, {"success": True, "url": _URL_CREADA})]
    return {
        "GET /login": [_FakeResp(200, {})] * 3,
        "POST /login": [_FakeResp(302, {})] * 3,
        "POST /api/payment-links": api,
    }


def test_crear_link_exitoso_devuelve_url(fake_session):
    fake_session(_respuestas_ok())
    cliente = ClientePanel(CONFIG)
    r = cliente.crear_link(nombre="MARIA LOPEZ", total=400.93, id_pedido=450)
    assert r.ok is True
    assert r.url == _URL_CREADA
    assert r.error is None


def test_crear_link_manda_el_payload_correcto(fake_session):
    creadas = fake_session(_respuestas_ok())
    ClientePanel(CONFIG).crear_link(nombre="MARIA LOPEZ", total=400.93, id_pedido=450)
    envios = [j for (m, u, j) in creadas[0].llamadas if "/api/payment-links" in u]
    assert envios[0]["description"] == "MARIA LOPEZ # 450"
    assert envios[0]["price"] == 400.93
    assert envios[0]["infile"] == 1


def test_credenciales_malas_devuelve_error_claro(fake_session):
    fake_session({
        "GET /login": [_FakeResp(200, {})],
        "POST /login": [_FakeResp(422, {"message": "credenciales inválidas"})],
    })
    r = ClientePanel(CONFIG).crear_link(nombre="ANA", total=10.0, id_pedido=1)
    assert r.ok is False
    assert "credencial" in r.error.lower()


def test_sesion_vencida_reloguea_y_reintenta(fake_session):
    creadas = fake_session(_respuestas_ok(extra_api=[
        _FakeResp(419, {}),  # sesión vencida en el primer intento
        _FakeResp(201, {"success": True, "url": _URL_CREADA}),
    ]))
    cliente = ClientePanel(CONFIG)
    r = cliente.crear_link(nombre="ANA", total=10.0, id_pedido=1)
    assert r.ok is True
    assert r.url == _URL_CREADA
    # Hubo dos sesiones: la vencida y la nueva tras el re-login.
    assert len(creadas) == 2


def test_sesion_se_reusa_entre_llamadas(fake_session):
    creadas = fake_session(_respuestas_ok(extra_api=[
        _FakeResp(201, {"success": True, "url": _URL_CREADA}),
        _FakeResp(201, {"success": True, "url": _URL_CREADA}),
    ]))
    cliente = ClientePanel(CONFIG)
    assert cliente.crear_link(nombre="ANA", total=10.0, id_pedido=1).ok
    assert cliente.crear_link(nombre="ANA", total=20.0, id_pedido=2).ok
    # Un solo login (una sola sesión creada) para las dos llamadas.
    assert len(creadas) == 1


def test_error_http_del_api_devuelve_ok_false(fake_session):
    fake_session(_respuestas_ok(extra_api=[_FakeResp(500, {})]))
    r = ClientePanel(CONFIG).crear_link(nombre="ANA", total=10.0, id_pedido=1)
    assert r.ok is False
    assert r.error


def test_respuesta_sin_url_devuelve_ok_false(fake_session):
    fake_session(_respuestas_ok(extra_api=[_FakeResp(201, {"success": True})]))
    r = ClientePanel(CONFIG).crear_link(nombre="ANA", total=10.0, id_pedido=1)
    assert r.ok is False
    assert r.error


def test_excepcion_de_red_devuelve_ok_false(fake_session, monkeypatch):
    creadas = fake_session(_respuestas_ok())

    def post_explota(url, **kw):
        raise qpaypro_panel.requests.RequestException("timeout")

    cliente = ClientePanel(CONFIG)
    # Deja pasar el login y truena el POST del API.
    r_ok = cliente.crear_link(nombre="ANA", total=10.0, id_pedido=1)
    assert r_ok.ok is True
    monkeypatch.setattr(creadas[0], "post", post_explota)
    r = cliente.crear_link(nombre="ANA", total=10.0, id_pedido=2)
    assert r.ok is False
    assert r.error
