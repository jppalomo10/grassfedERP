"""Pruebas de la generación del mensaje de cobro (función pura)."""
from mensajes import generar_mensaje_cobro, DATOS_BANCARIOS


def test_transferencia_incluye_datos_bancarios_y_comprobante():
    msg = generar_mensaje_cobro(
        nombre="María López",
        total=550.0,
        metodo_pago="Transferencia",
        titulo="Doña",
    )
    assert "Buen día Doña María López" in msg
    assert "GTQ 550.00" in msg
    # Datos de la cuenta de Banrural / PRODECA
    assert "Banrural" in msg
    assert "3256009530" in msg
    assert "PRODECA" in msg
    # Se pide el comprobante
    assert "comprobante de pago" in msg


def test_tarjeta_con_link_incluye_el_link():
    msg = generar_mensaje_cobro(
        nombre="José Pérez",
        total=675.0,
        metodo_pago="Tarjeta",
        titulo="Don",
        link_tarjeta="https://pago.example/abc",
    )
    assert "Buen día Don José Pérez" in msg
    assert "GTQ 675.00" in msg
    assert "https://pago.example/abc" in msg
    assert "tarjeta" in msg.lower()
    assert "comprobante de pago" in msg
    # No debe mezclar datos de transferencia
    assert "3256009530" not in msg


def test_tarjeta_sin_link_no_rompe_y_avisa_envio():
    msg = generar_mensaje_cobro(
        nombre="Ana",
        total=100.0,
        metodo_pago="Tarjeta",
        titulo="Doña",
        link_tarjeta="",
    )
    assert "GTQ 100.00" in msg
    assert "tarjeta" in msg.lower()
    # Sin link, debe indicar que se enviará el link
    assert "enviaremos" in msg.lower()


def test_efectivo_sin_datos_de_pago_ni_comprobante():
    msg = generar_mensaje_cobro(
        nombre="Pedro",
        total=300.0,
        metodo_pago="Efectivo",
        titulo="Don",
    )
    assert "Buen día Don Pedro" in msg
    assert "GTQ 300.00" in msg
    assert "3256009530" not in msg
    assert "comprobante de pago" not in msg


def test_titulo_por_defecto_es_dona():
    msg = generar_mensaje_cobro(nombre="Lucía", total=50.0, metodo_pago="Efectivo")
    assert "Buen día Doña Lucía" in msg


def test_total_se_formatea_con_separador_de_miles():
    msg = generar_mensaje_cobro(
        nombre="Carlos", total=1234.5, metodo_pago="Efectivo", titulo="Don"
    )
    assert "GTQ 1,234.50" in msg


def test_datos_bancarios_constante():
    assert DATOS_BANCARIOS["numero"] == "3256009530"
    assert DATOS_BANCARIOS["nombre"] == "PRODECA"
    assert DATOS_BANCARIOS["banco"] == "Banrural"
