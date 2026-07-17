"""Pruebas de la lógica pura de ui_mensajes (vigencia del link generado).

El link generado se cachea en session_state; si el total o el pedido cambian
después de generarlo, el link viejo cobraría un monto equivocado y debe
descartarse. Esa decisión es pura y se prueba aquí; el render de Streamlit no.
"""
from ui_mensajes import _link_generado_vigente


_GUARDADO = {
    "url": "https://payments.qpaypro.com/checkout/dK6w2o6u42yB3688/451680",
    "total": 535.00,
    "id_pedido": 450,
}


def test_link_vigente_si_total_y_pedido_coinciden():
    assert _link_generado_vigente(_GUARDADO, 535.00, 450) == _GUARDADO["url"]


def test_link_descartado_si_cambia_el_total():
    assert _link_generado_vigente(_GUARDADO, 600.00, 450) is None


def test_link_descartado_si_cambia_el_pedido():
    assert _link_generado_vigente(_GUARDADO, 535.00, 451) is None


def test_sin_guardado_devuelve_none():
    assert _link_generado_vigente(None, 535.00, 450) is None
    assert _link_generado_vigente({}, 535.00, 450) is None


def test_total_decimal_o_float_no_importa_redondeo():
    from decimal import Decimal
    assert _link_generado_vigente(_GUARDADO, Decimal("535.00"), 450) == _GUARDADO["url"]
    # Deriva de float minúscula no invalida el link.
    assert _link_generado_vigente(_GUARDADO, 535.0000001, 450) == _GUARDADO["url"]
