"""Hoja de etiquetas QR para imprimir sobre adhesivo Avery 5160 (Letter).

Se dibuja con el `canvas` de ReportLab en lugar de con `platypus` porque aquí
no hay flujo de texto que repaginar: hay una rejilla de posiciones físicas fijas
que tienen que caer sobre unos adhesivos ya troquelados. Colocar cada elemento
por coordenadas absolutas es lo que permite decir "este QR mide 21 mm" y que
mida 21 mm en el papel.

Los módulos del QR se pintan como rectángulos, no como una imagen escalada:
una imagen reescalada por el driver de impresión difumina los bordes, y a
0,6 mm de módulo eso es la diferencia entre que el teléfono lea el código al
primer intento o no lo lea.
"""

import io
from datetime import datetime

from django.http import HttpResponse
from reportlab.lib.colors import HexColor, black
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch, mm
from reportlab.pdfgen import canvas as canvas_pdf

from activos.services import qr as servicio_qr

# --- Geometría Avery 5160 / 5260 sobre hoja Letter --------------------------
# Medidas del fabricante en pulgadas; se convierten a puntos una sola vez.

COLUMNAS = 3
FILAS = 10

MARGEN_IZQUIERDO = 0.1875 * inch
MARGEN_SUPERIOR = 0.5 * inch

ANCHO_ETIQUETA = 2.625 * inch
ALTO_ETIQUETA = 1.0 * inch

#: Distancia entre orígenes de dos etiquetas contiguas. En vertical coincide con
#: el alto porque este formato no deja calle entre filas.
PASO_HORIZONTAL = 2.75 * inch
PASO_VERTICAL = 1.0 * inch

#: Aire interior. Los troqueles se desvían hasta ~0,5 mm entre lotes de papel,
#: así que nada útil debe acercarse más que esto al borde.
RESPIRO = 2.2 * mm

#: Lado del QR. Con una URL de ~41 caracteres y corrección Q el símbolo ronda
#: los 33-37 módulos, lo que deja ~0,58-0,65 mm por módulo: por encima del
#: mínimo práctico de una láser de 600 ppp.
LADO_QR = ALTO_ETIQUETA - (2 * RESPIRO)

AZUL_PALDACA = HexColor("#32407b")
GRIS_TENUE = HexColor("#8a91a4")


def _dibujar_qr(lienzo, etiqueta, x, y, lado):
    """Pinta el símbolo como rectángulos negros dentro del cuadrado dado."""
    matriz = servicio_qr.matriz(etiqueta)
    if not matriz:
        return
    modulos = len(matriz)
    paso = lado / modulos

    lienzo.setFillColor(black)
    for indice_fila, fila in enumerate(matriz):
        # El origen de ReportLab está abajo; la matriz se recorre de arriba
        # abajo, de ahí la inversión del eje vertical.
        cima = y + lado - (indice_fila + 1) * paso
        inicio = None
        for indice_col in range(modulos + 1):
            oscuro = indice_col < modulos and fila[indice_col]
            if oscuro and inicio is None:
                inicio = indice_col
            elif not oscuro and inicio is not None:
                # Se agrupan módulos contiguos en un solo rectángulo: reduce
                # mucho el peso del PDF y evita costuras blancas entre celdas.
                lienzo.rect(
                    x + inicio * paso,
                    cima,
                    (indice_col - inicio) * paso,
                    paso,
                    stroke=0,
                    fill=1,
                )
                inicio = None


def _dibujar_etiqueta(lienzo, etiqueta, x, y):
    """Una etiqueta: QR a la izquierda, identificación a la derecha."""
    _dibujar_qr(lienzo, etiqueta, x + RESPIRO, y + RESPIRO, LADO_QR)

    texto_x = x + RESPIRO + LADO_QR + (2.2 * mm)
    ancho_texto = ANCHO_ETIQUETA - (texto_x - x) - RESPIRO
    if ancho_texto <= 0:
        return

    lienzo.setFillColor(AZUL_PALDACA)
    lienzo.setFont("Helvetica-Bold", 5.4)
    lienzo.drawString(texto_x, y + ALTO_ETIQUETA - RESPIRO - 4.4, "CONSORCIO PALDACA")

    # El código legible es lo que se usa en un inventario físico con portapapeles,
    # cuando nadie quiere sacar el teléfono para cada equipo.
    lienzo.setFillColor(black)
    lienzo.setFont("Helvetica-Bold", 10)
    lienzo.drawString(texto_x, y + ALTO_ETIQUETA - RESPIRO - 15, etiqueta.codigo_reservado)

    lienzo.setFillColor(GRIS_TENUE)
    lienzo.setFont("Helvetica", 6)
    nombre = etiqueta.subcategoria.nombre
    while nombre and lienzo.stringWidth(nombre, "Helvetica", 6) > ancho_texto:
        nombre = nombre[:-1]
    lienzo.drawString(texto_x, y + ALTO_ETIQUETA - RESPIRO - 23.5, nombre)

    lienzo.setFont("Helvetica", 5.2)
    lienzo.drawString(texto_x, y + RESPIRO + 1.5, "Escanea para ver la ficha")


def generar_hoja_etiquetas(etiquetas, filename=None) -> HttpResponse:
    """PDF con las etiquetas dispuestas en la rejilla Avery 5160.

    Se rellena por filas (izquierda a derecha, arriba a abajo) siguiendo el
    orden en que se despega una hoja.
    """
    etiquetas = list(etiquetas)
    if not etiquetas:
        raise ValueError("No hay etiquetas que imprimir.")

    buffer = io.BytesIO()
    lienzo = canvas_pdf.Canvas(buffer, pagesize=letter)
    lienzo.setTitle("Etiquetas QR de activos")

    _, alto_pagina = letter
    por_hoja = COLUMNAS * FILAS

    for indice, etiqueta in enumerate(etiquetas):
        if indice and indice % por_hoja == 0:
            lienzo.showPage()

        posicion = indice % por_hoja
        fila, columna = divmod(posicion, COLUMNAS)

        x = MARGEN_IZQUIERDO + columna * PASO_HORIZONTAL
        # Coordenada de la ESQUINA INFERIOR izquierda de la celda.
        y = alto_pagina - MARGEN_SUPERIOR - (fila + 1) * PASO_VERTICAL

        _dibujar_etiqueta(lienzo, etiqueta, x, y)

    lienzo.showPage()
    lienzo.save()

    nombre = filename or f"etiquetas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    respuesta = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    # `inline` y no `attachment`: lo primero que hace quien genera un lote es
    # mirarlo antes de mandarlo a la impresora.
    respuesta["Content-Disposition"] = f'inline; filename="{nombre}"'
    return respuesta
