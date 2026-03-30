"""
Utilidades para generación de factura PDF con ReportLab.
Módulo compartido entre las páginas de Streamlit.
"""

from io import BytesIO
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.colors import Color, white
from reportlab.platypus import Table, TableStyle
from reportlab.pdfgen import canvas


costos_envio = {"Ciudad": 30, "Antigua Guatemala": 80, "Metropolitano": 40}


def generar_factura_pdf(id_pedido, fecha, cliente_nombre, cliente_tel,
                        cliente_dir, metodo_pago, lineas, total, envio):
    """Genera un PDF tipo factura con ReportLab y devuelve un BytesIO."""

    # ── Colores de marca ─────────────────────────────────────────────
    VERDE = Color(84 / 255, 98 / 255, 50 / 255)
    MARRON = Color(26 / 255, 21 / 255, 16 / 255)
    GRIS_CLARO = Color(245 / 255, 240 / 255, 233 / 255)
    GRIS_TEXTO = Color(140 / 255, 140 / 255, 140 / 255)

    PAGE_W, PAGE_H = LETTER  # 612 x 792 points
    MARGIN = 40

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)

    usable_w = PAGE_W - 2 * MARGIN

    # ── Encabezado con banda verde ───────────────────────────────────
    header_h = 110
    c.setFillColor(VERDE)
    c.rect(0, PAGE_H - header_h, PAGE_W, header_h, fill=1, stroke=0)

    # Título izquierdo
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(MARGIN, PAGE_H - 40, "GrassFed GT")

    # Info derecha
    c.setFont("Helvetica", 11)
    right_x = PAGE_W - MARGIN
    c.drawRightString(right_x, PAGE_H - 40, f"Factura  #{id_pedido}")
    fecha_str = fecha.strftime('%d/%m/%Y') if hasattr(fecha, 'strftime') else str(fecha)
    c.drawRightString(right_x, PAGE_H - 56, f"Fecha: {fecha_str}")
    c.drawRightString(right_x, PAGE_H - 72, f"Pago: {metodo_pago}")

    y = PAGE_H - header_h - 30

    # ── Datos del cliente ────────────────────────────────────────────
    c.setFillColor(MARRON)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(MARGIN, y, "Datos del cliente")
    y -= 4
    c.setStrokeColor(VERDE)
    c.setLineWidth(1.5)
    c.line(MARGIN, y, PAGE_W - MARGIN, y)
    y -= 18

    info_labels = ["Nombre:", "Telefono:", "Direccion:"]
    info_values = [str(cliente_nombre), str(cliente_tel), str(cliente_dir)]
    for lab, val in zip(info_labels, info_values):
        c.setFont("Helvetica-Bold", 10)
        c.drawString(MARGIN, y, lab)
        c.setFont("Helvetica", 10)
        c.drawString(MARGIN + 70, y, val)
        y -= 16

    y -= 14

    # ── Tabla de detalle ─────────────────────────────────────────────
    c.setFillColor(MARRON)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(MARGIN, y, "Detalle de productos")
    y -= 4
    c.setStrokeColor(VERDE)
    c.line(MARGIN, y, PAGE_W - MARGIN, y)
    y -= 8

    # Construir datos de la tabla
    headers = ["#", "Producto", "Cant.", "Peso (lb)", "Precio", "Desc. (Q)", "Subtotal"]
    table_data = [headers]

    for idx, l in enumerate(lineas, 1):
        table_data.append([
            str(idx),
            str(l["Producto"]),
            str(l["Cantidad"]),
            f"{l['Peso (lb)']:.2f}",
            f"Q{l['Precio']:,.2f}",
            f"Q{l['Descuento (%)']:,.2f}",
            f"Q{l['Subtotal']:,.2f}",
        ])

    # Anchos de columna proporcionales
    col_widths = [
        usable_w * 0.06,   # #
        usable_w * 0.30,   # Producto
        usable_w * 0.10,   # Cantidad
        usable_w * 0.12,   # Peso
        usable_w * 0.14,   # Precio
        usable_w * 0.14,   # Descuento
        usable_w * 0.14,   # Subtotal
    ]

    table = Table(table_data, colWidths=col_widths)

    # Estilos de la tabla
    style_cmds = [
        # Cabecera
        ('BACKGROUND', (0, 0), (-1, 0), VERDE),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (0, 0), (1, 0), 'LEFT'),
        ('ALIGN', (2, 0), (-1, 0), 'CENTER'),
        # Cuerpo
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('TEXTCOLOR', (0, 1), (-1, -1), MARRON),
        ('ALIGN', (2, 1), (3, -1), 'CENTER'),
        ('ALIGN', (4, 1), (-1, -1), 'RIGHT'),
        # Bordes y padding
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        ('LINEBELOW', (0, -1), (-1, -1), 1.5, VERDE),
    ]

    # Filas alternas
    for i in range(1, len(table_data)):
        if i % 2 == 0:
            style_cmds.append(('BACKGROUND', (0, i), (-1, i), GRIS_CLARO))

    table.setStyle(TableStyle(style_cmds))

    # Calcular alto de la tabla y dibujarla
    tw, th = table.wrap(usable_w, y)
    table.drawOn(c, MARGIN, y - th)
    y = y - th - 20

    # ── Costo de envío ───────────────────────────────────────────────
    envio_costo = costos_envio.get(envio, 0)
    c.setFillColor(MARRON)
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(PAGE_W - MARGIN - 90, y, "ENVIO:")
    c.setFont("Helvetica", 12)
    c.drawRightString(PAGE_W - MARGIN, y, f"Q{envio_costo:,.2f}")
    y -= 24

    # ── Total ────────────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(PAGE_W - MARGIN - 90, y, "TOTAL:")
    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(PAGE_W - MARGIN, y, f"Q{total:,.2f}")
    y -= 40

    # ── Pie de página ────────────────────────────────────────────────
    c.setFillColor(GRIS_TEXTO)
    c.setFont("Helvetica-Oblique", 8)
    c.drawCentredString(
        PAGE_W / 2, MARGIN - 10,
        "GrassFed GT  |  Carne 100% libre de hormonas  |  grassfedgt.com"
    )

    c.save()
    buf.seek(0)
    return buf
