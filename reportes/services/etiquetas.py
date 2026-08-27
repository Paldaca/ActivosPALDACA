"""Hoja de etiquetas QR para imprimir sobre adhesivo Avery 5160 (Letter).

Se dibuja con el `canvas` de ReportLab en lugar de con `platypus` porque aquí
no hay flujo de texto que repaginar: hay una rejilla de posiciones físicas fijas
que tienen que caer sobre unos adhesivos ya troquelados. Colocar cada elemento
por coordenadas absolutas es lo que permite decir "este QR mide 21 mm" y que
mida 21 mm en el papel.

Cada etiqueta lleva ÚNICAMENTE el símbolo, centrado en el adhesivo. Sin código
legible ni texto de acompañamiento: la marca ya integrada en el QR basta para
identificarlo, y menos elementos es menos que se desalinee entre lotes de
papel.

El símbolo se dibuja como vectores, no como una imagen escalada: una imagen
reescalada por el driver de impresión difumina los bordes, y a medio milímetro
de módulo eso es la diferencia entre que el teléfono lea el código al primer
intento o no lo lea.
"""

import io
from datetime import datetime

from django.http import HttpResponse
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch, mm
from reportlab.lib.utils import ImageReader
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

#: Lado del QR. Con la URL pública y corrección H el símbolo son 41 módulos,
#: lo que deja ~0,51 mm por módulo: verificado decodificando el resultado
#: rasterizado a 300, 600 y 1200 ppp.
LADO_QR = ALTO_ETIQUETA - (2 * RESPIRO)


def _cargar_marca():
    """`ImageReader` de la marca, o None si el fichero no está.

    Se carga UNA vez por hoja y se reutiliza en cada etiqueta: ReportLab
    incrusta una copia del PNG por cada ruta distinta que se le pasa, así que
    dibujar 30 veces desde el disco multiplicaba por 30 el peso del PDF.

    Devuelve None en lugar de fallar porque un QR sin marca se sigue leyendo:
    a un despliegue al que le falte el fichero le vale más imprimir etiquetas
    válidas y sin marca que no imprimir nada.
    """
    ruta = servicio_qr.ruta_logo_disco()
    return ImageReader(ruta) if ruta else None


#: Nombre del XObject que guarda un punto dibujado una sola vez.
FORMA_PUNTO = "axPuntoQR"


def _definir_punto(lienzo, radio):
    """Guarda UN punto en el PDF para luego colocarlo por referencia.

    Cada símbolo tiene ~530 puntos y cada círculo son cuatro curvas Bézier
    escritas como texto: dibujarlos uno a uno deja una hoja llena en ~900 KB.
    Definiéndolo como XObject, cada punto pasa a ser una matriz de traslación
    y una llamada, y la misma hoja baja a ~70 KB. El color se fija aquí porque
    queda horneado dentro de la forma.
    """
    lienzo.beginForm(FORMA_PUNTO, -radio, -radio, radio, radio)
    lienzo.setFillColor(HexColor(servicio_qr.AZUL))
    lienzo.circle(0, 0, radio, stroke=0, fill=1)
    lienzo.endForm()


def _dibujar_qr(lienzo, p, marca, x, y, lado):
    """Dibuja el símbolo con el mismo estilo que la versión de pantalla.

    Recibe el `Plano` ya resuelto en vez de la etiqueta: quien llama necesita
    conocerlo antes para definir el punto con el radio correcto, y calcularlo
    dos veces por etiqueta sería tirar trabajo.
    """
    u = lado / p.lado  # puntos PDF por módulo

    # El origen de ReportLab está abajo y el del plano arriba: esta función
    # invierte el eje una sola vez, para no repetir la resta en cada figura.
    def cy(fila):
        return y + lado - fila * u

    for mx, my in p.puntos:
        lienzo.saveState()
        lienzo.translate(x + mx * u, cy(my))
        lienzo.doForm(FORMA_PUNTO)
        lienzo.restoreState()

    rojo = HexColor(servicio_qr.ROJO)
    ojo = servicio_qr.OJO
    anillo = servicio_qr.OJO_RADIO_ANILLO
    for ox, oy in p.ojos:
        # Tres figuras macizas superpuestas, nunca un anillo trazado: trazar la
        # línea deforma la proporción 1:1:3:1:1 que el lector busca para
        # localizar el símbolo, y deja de leerse.
        for margen, lado_ojo, radio, color in (
            (0, ojo, anillo, rojo),
            (1, ojo - 2, max(0, anillo - 1), white),
            (2, ojo - 4, servicio_qr.OJO_RADIO_NUCLEO, rojo),
        ):
            lienzo.setFillColor(color)
            lienzo.roundRect(
                x + (ox + margen) * u,
                cy(oy + margen + lado_ojo),
                lado_ojo * u,
                lado_ojo * u,
                radio * u,
                stroke=0,
                fill=1,
            )

    if marca is None:
        return

    # La marca se apoya sobre el hueco que `plano()` dejó vacío: no hay placa
    # blanca que tapar nada, que es lo que la integra en el símbolo en vez de
    # parecer un parche encima.
    hx, hy, hlado = p.hueco
    lado_marca = hlado * servicio_qr.MARCA_EN_HUECO * u
    centrado = (hlado * u - lado_marca) / 2
    lienzo.drawImage(
        marca,
        x + hx * u + centrado,
        cy(hy + hlado) + centrado,
        width=lado_marca,
        height=lado_marca,
        # La marca es más ancha que alta: sin esto se deformaría al cuadrarla.
        preserveAspectRatio=True,
        # Respeta el canal alfa del PNG; si no, el recorte saldría en negro.
        mask="auto",
    )


def _dibujar_etiqueta(lienzo, etiqueta, plano, marca, x, y):
    """Una etiqueta: solo el símbolo, centrado en el adhesivo.

    Sin código legible ni texto de acompañamiento a propósito: el QR ya lleva
    la marca y basta por sí solo para identificar y abrir la ficha del
    activo. Menos elementos también significa menos que se desalinee si el
    troquel del papel se desvía entre lotes.
    """
    centrado_x = x + (ANCHO_ETIQUETA - LADO_QR) / 2
    centrado_y = y + (ALTO_ETIQUETA - LADO_QR) / 2
    _dibujar_qr(lienzo, plano, marca, centrado_x, centrado_y, LADO_QR)


def generar_hoja_etiquetas(etiquetas, filename=None) -> HttpResponse:
    """PDF con las etiquetas dispuestas en la rejilla Avery 5160.

    Se rellena por filas (izquierda a derecha, arriba a abajo) siguiendo el
    orden en que se despega una hoja.
    """
    etiquetas = list(etiquetas)
    if not etiquetas:
        raise ValueError("No hay etiquetas que imprimir.")

    # Los planos se resuelven antes de abrir el lienzo porque el punto
    # reutilizable hay que definirlo con su radio ya conocido, y ese radio sale
    # de cuántos módulos tiene el símbolo.
    planos = [servicio_qr.plano(e) for e in etiquetas]
    lados = {p.lado for p in planos}
    if len(lados) > 1:
        raise ValueError(
            "Las etiquetas de una misma hoja deben tener el mismo número de "
            f"módulos; se recibieron {sorted(lados)}."
        )

    buffer = io.BytesIO()
    lienzo = canvas_pdf.Canvas(buffer, pagesize=letter, pageCompression=1)
    lienzo.setTitle("Etiquetas QR de activos")
    _definir_punto(lienzo, servicio_qr.DIAMETRO_PUNTO / 2 * LADO_QR / lados.pop())
    marca = _cargar_marca()

    _, alto_pagina = letter
    por_hoja = COLUMNAS * FILAS

    for indice, (etiqueta, plano) in enumerate(zip(etiquetas, planos)):
        if indice and indice % por_hoja == 0:
            lienzo.showPage()

        posicion = indice % por_hoja
        fila, columna = divmod(posicion, COLUMNAS)

        x = MARGEN_IZQUIERDO + columna * PASO_HORIZONTAL
        # Coordenada de la ESQUINA INFERIOR izquierda de la celda.
        y = alto_pagina - MARGEN_SUPERIOR - (fila + 1) * PASO_VERTICAL

        _dibujar_etiqueta(lienzo, etiqueta, plano, marca, x, y)

    lienzo.showPage()
    lienzo.save()

    nombre = filename or f"etiquetas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    respuesta = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    # `inline` y no `attachment`: lo primero que hace quien genera un lote es
    # mirarlo antes de mandarlo a la impresora.
    respuesta["Content-Disposition"] = f'inline; filename="{nombre}"'
    return respuesta
