"""Pruebas del cliente de QPayPro (generación de links de pago).

`construir_payload` es una función pura y se prueba sin red.
`generar_link_pago` hace un POST; se mockea `requests.post` (única frontera de I/O).
"""
import json

import pytest

import qpaypro
from qpaypro import construir_payload, generar_link_pago


CONFIG = {
    "entorno": "sandbox",
    "x_login": "visanetgt_qpay",
    "x_api_key": "88888888888",
    "email_relleno": "cf@grassfedgt.com",
}


# --------------------------------------------------------------------------
# construir_payload (función pura)
# --------------------------------------------------------------------------

def test_payload_incluye_credenciales_monto_moneda_y_store_type():
    p = construir_payload(
        nombre="JOSE PEREZ", telefono="12345678", total=535.0,
        id_pedido=123, correo="", config=CONFIG,
    )
    assert p["x_login"] == "visanetgt_qpay"
    assert p["x_api_key"] == "88888888888"
    assert p["x_amount"] == "535.00"
    assert p["x_currency_code"] == "GTQ"
    assert p["store_type"] == "hostedpage"


def test_payload_monto_se_formatea_con_dos_decimales():
    p = construir_payload(
        nombre="ANA", telefono="55550000", total=1234.5,
        id_pedido=1, config=CONFIG,
    )
    assert p["x_amount"] == "1234.50"


def test_payload_separa_nombre_en_first_y_last():
    p = construir_payload(
        nombre="JOSE PEREZ", telefono="12345678", total=10.0,
        id_pedido=1, config=CONFIG,
    )
    assert p["x_first_name"] == "JOSE"
    assert p["x_last_name"] == "PEREZ"


def test_payload_last_name_relleno_cuando_no_hay_apellido():
    p = construir_payload(
        nombre="MADONNA", telefono="12345678", total=10.0,
        id_pedido=1, config=CONFIG,
    )
    assert p["x_first_name"] == "MADONNA"
    # La API exige x_last_name; usamos relleno cuando no hay apellido.
    assert p["x_last_name"].strip() != ""


def test_payload_sanitiza_telefono_a_solo_digitos():
    p = construir_payload(
        nombre="JOSE PEREZ", telefono="+502 1234-5678", total=10.0,
        id_pedido=1, config=CONFIG,
    )
    assert p["x_phone"] == "50212345678"


def test_payload_usa_email_relleno_cuando_no_hay_correo():
    p = construir_payload(
        nombre="JOSE PEREZ", telefono="12345678", total=10.0,
        id_pedido=1, correo="", config=CONFIG,
    )
    assert p["x_email"] == "cf@grassfedgt.com"


def test_payload_usa_correo_del_cliente_cuando_existe():
    p = construir_payload(
        nombre="JOSE PEREZ", telefono="12345678", total=10.0,
        id_pedido=1, correo="jose@example.com", config=CONFIG,
    )
    assert p["x_email"] == "jose@example.com"


def test_payload_descripcion_formato_nombre_y_pedido():
    p = construir_payload(
        nombre="JOSE PEREZ", telefono="12345678", total=10.0,
        id_pedido=448, config=CONFIG,
    )
    # Replica la convención del panel: "NOMBRE # PEDIDO".
    assert p["x_description"] == "JOSE PEREZ # 448"
    assert p["x_invoice_num"] == "448"


def test_payload_descripcion_sin_sufijo_cuando_no_hay_pedido():
    p = construir_payload(
        nombre="JOSE PEREZ", telefono="12345678", total=10.0,
        id_pedido=None, config=CONFIG,
    )
    assert "#" not in p["x_description"]
    assert p["x_description"] == "JOSE PEREZ"


def test_payload_products_incluye_nombre_producto_y_monto():
    p = construir_payload(
        nombre="JOSE PEREZ", telefono="12345678", total=535.0,
        id_pedido=1, config=CONFIG,
    )
    # products es un arreglo JSON escapado (string).
    productos = json.loads(p["products"])
    assert productos[0][0] == "Caja surtida de carne de pastoreo"
    assert productos[0][1] == "535.00"


def test_payload_nombre_producto_configurable():
    cfg = {**CONFIG, "nombre_producto": "Media caja surtida"}
    p = construir_payload(
        nombre="JOSE PEREZ", telefono="12345678", total=10.0,
        id_pedido=1, config=cfg,
    )
    productos = json.loads(p["products"])
    assert productos[0][0] == "Media caja surtida"


# La API exige estos campos aunque la doc no los marque con (*). Descubierto
# empíricamente al recibir HTTP 400 del sandbox.
_CAMPOS_REQUERIDOS_API = (
    "x_url_cancel", "http_origin", "x_company", "x_address",
    "x_city", "x_state", "x_zip", "taxes", "origen",
)


def test_payload_incluye_todos_los_campos_requeridos_por_la_api():
    p = construir_payload(
        nombre="JOSE PEREZ", telefono="12345678", total=10.0,
        id_pedido=1, config=CONFIG,
    )
    for campo in _CAMPOS_REQUERIDOS_API:
        assert campo in p, f"falta el campo requerido {campo}"
        assert str(p[campo]).strip() != "", f"{campo} no puede ir vacío"


def test_payload_http_origin_y_url_retorno_configurables():
    cfg = {
        **CONFIG,
        "http_origin": "mitienda.com",
        "url_retorno": "https://mitienda.com/gracias",
    }
    p = construir_payload(
        nombre="JOSE PEREZ", telefono="12345678", total=10.0,
        id_pedido=1, config=cfg,
    )
    assert p["http_origin"] == "mitienda.com"
    assert p["x_url_cancel"] == "https://mitienda.com/gracias"


# --------------------------------------------------------------------------
# generar_link_pago (POST mockeado)
# --------------------------------------------------------------------------

class _FakeResp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


def _patch_post(monkeypatch, resp=None, exc=None):
    def fake_post(url, *args, **kwargs):
        if exc is not None:
            raise exc
        fake_post.llamado_con = {"url": url, "kwargs": kwargs}
        return resp
    monkeypatch.setattr(qpaypro.requests, "post", fake_post)
    return fake_post


def test_generar_link_exito_devuelve_url_con_token(monkeypatch):
    _patch_post(monkeypatch, resp=_FakeResp(200, {"token": "abc123"}))
    r = generar_link_pago(
        nombre="JOSE PEREZ", telefono="12345678", total=535.0,
        id_pedido=1, config=CONFIG,
    )
    assert r.ok is True
    assert r.url == "https://sandboxpayments.qpaypro.com/checkout/store?token=abc123"
    assert r.error is None


def test_generar_link_token_anidado_en_response_object(monkeypatch):
    _patch_post(monkeypatch, resp=_FakeResp(200, {"responseObject": {"token": "xyz"}}))
    r = generar_link_pago(
        nombre="JOSE PEREZ", telefono="12345678", total=535.0,
        id_pedido=1, config=CONFIG,
    )
    assert r.ok is True
    assert r.url.endswith("token=xyz")


def test_generar_link_con_forma_real_de_respuesta_sandbox(monkeypatch):
    # Forma real confirmada contra el sandbox de QPayPro (2026-07-03):
    # {"estado":"success","data":{"token":"..."}}
    real = {"estado": "success", "data": {"token": "03d80b4d1cef89dfe15926305a26911f"}}
    _patch_post(monkeypatch, resp=_FakeResp(200, real))
    r = generar_link_pago(
        nombre="JUAN PEREZ", telefono="12345678", total=535.0,
        id_pedido=448, config=CONFIG,
    )
    assert r.ok is True
    assert r.url == (
        "https://sandboxpayments.qpaypro.com/checkout/store"
        "?token=03d80b4d1cef89dfe15926305a26911f"
    )


def test_generar_link_usa_host_de_produccion_segun_entorno(monkeypatch):
    cfg = {**CONFIG, "entorno": "produccion"}
    _patch_post(monkeypatch, resp=_FakeResp(200, {"token": "prodtoken"}))
    r = generar_link_pago(
        nombre="JOSE PEREZ", telefono="12345678", total=535.0,
        id_pedido=1, config=cfg,
    )
    assert r.url == "https://payments.qpaypro.com/checkout/store?token=prodtoken"


def test_generar_link_error_http_devuelve_ok_false(monkeypatch):
    _patch_post(monkeypatch, resp=_FakeResp(500, {"error": "boom"}))
    r = generar_link_pago(
        nombre="JOSE PEREZ", telefono="12345678", total=10.0,
        id_pedido=1, config=CONFIG,
    )
    assert r.ok is False
    assert r.url is None
    assert r.error


def test_generar_link_excepcion_de_red_devuelve_ok_false(monkeypatch):
    _patch_post(monkeypatch, exc=qpaypro.requests.RequestException("timeout"))
    r = generar_link_pago(
        nombre="JOSE PEREZ", telefono="12345678", total=10.0,
        id_pedido=1, config=CONFIG,
    )
    assert r.ok is False
    assert r.error


def test_generar_link_respuesta_sin_token_devuelve_ok_false(monkeypatch):
    _patch_post(monkeypatch, resp=_FakeResp(200, {"algo": "otro"}))
    r = generar_link_pago(
        nombre="JOSE PEREZ", telefono="12345678", total=10.0,
        id_pedido=1, config=CONFIG,
    )
    assert r.ok is False
    assert r.error
