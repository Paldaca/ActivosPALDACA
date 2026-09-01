"""Generación de códigos QR para las etiquetas de activos.

Único punto donde se decide qué se codifica, con qué parámetros y con qué
aspecto. Aislarlo importa por dos motivos: los parámetros están atados a una
restricción física —cada celda de la hoja Letter mide ~52 × 25 mm (4 columnas)— y el mismo
dibujo tiene que salir idéntico en pantalla (SVG) y en papel (ReportLab).

De ahí `plano()`: resuelve la geometría una sola vez y devuelve primitivas que
los dos renderizadores consumen. Sin eso, el estilo se duplicaría en dos
ficheros y divergiría a la primera corrección.

Aquí NO se lee ningún QR: el escaneo lo hace la cámara del teléfono. Por eso no
entra ninguna dependencia de visión por computadora (`opencv`, `pyzbar`), que
en `python:3.13-slim` arrastraría librerías del sistema.
"""

import os
from urllib.parse import urljoin

import segno
from django.conf import settings
from django.templatetags.static import static
from django.urls import reverse

#: Corrección de errores. 'H' (30 %) porque el estilo de puntos y el hueco de
#: la marca restan información al símbolo. Sale barato: con esta URL, H solo
#: sube de la versión 4 a la 5.
NIVEL_CORRECCION = "h"

#: Zona de silencio en módulos. El estándar pide 4; a 21 mm de lado eso se come
#: demasiada superficie útil, y el blanco del propio adhesivo aporta el margen
#: óptico que falta. Verificar con impresión real antes de bajar de 2.
ZONA_SILENCIO = 2

#: Diámetro del punto respecto al paso del módulo. Por debajo de 1 aparece la
#: calle blanca que da el aire del estilo; bajarlo mucho adelgaza el trazo y en
#: papel el punto se pierde antes que un cuadrado del mismo tamaño.
DIAMETRO_PUNTO = 0.86

#: Lado del hueco central, en módulos. Ahí no se dibuja nada: la marca se apoya
#: sobre el blanco del fondo, sin placa. Es lo que la integra en el símbolo en
#: lugar de parchearlo. 9 módulos sobre 41 ≈ 4,8 % del área.
HUECO_MODULOS = 9

#: Lado de la marca respecto al hueco. Menor que 1 para que le quede aire.
MARCA_EN_HUECO = 0.92

#: Redondeo de los patrones de búsqueda, en módulos: el anillo exterior y el
#: núcleo. Un núcleo de 3 módulos con radio 1,5 es un círculo exacto.
#:
#: Los ojos se dibujan como figuras MACIZAS superpuestas —cuadrado exterior,
#: hueco blanco, núcleo—, nunca como un anillo trazado. Trazar la línea
#: deforma la proporción 1:1:3:1:1 que los lectores buscan para localizar el
#: símbolo, y el código deja de leerse por muy correctos que sean los datos.
OJO_RADIO_ANILLO = 0.8
OJO_RADIO_NUCLEO = 0.7

#: Colores de la propia marca CP, muestreados del PNG.
AZUL = "#313F7C"
ROJO = "#ED2446"

#: La marca sola, sin el texto del logotipo y con fondo transparente. Se generó
#: recortando `logo_paldaca.png`; a este tamaño el texto sería ilegible y solo
#: robaría módulos.
LOGO_ESTATICO = "core/img/marca_cp.png"

#: Lado del patrón de búsqueda, en módulos. Lo fija el estándar.
OJO = 7

#: Tipografía del código legible sobre el símbolo en la hoja Avery (ver
#: reportes/services/etiquetas.py). Va en el margen superior, sin achicar el QR.
TAMANO_FUENTE_CODIGO_PT = 5


def codigo_inventario_etiqueta(etiqueta) -> str:
    """Código de inventario legible para imprimir sobre el QR."""
    return (etiqueta.codigo_reservado or "").strip().upper()


def url_publica(etiqueta) -> str:
    """URL absoluta que se imprime en el QR.

    Se construye desde `PALDACA_PUBLIC_BASE_URL` y NO desde el `Host` de la
    petición: la etiqueta se imprime una vez y se pega para siempre, así que no
    puede depender de por dónde entró quien pulsó "imprimir". En concreto, si
    se generase desde una petición servida dentro del shell del Portal, el QR
    apuntaría a una ruta que sólo funciona con sesión.
    """
    ruta = reverse("etiqueta-publica", kwargs={"token": etiqueta.token})
    base = (getattr(settings, "PALDACA_PUBLIC_BASE_URL", "") or "").strip()
    if not base:
        return ruta
    return urljoin(f"{base.rstrip('/')}/", ruta.lstrip("/"))


def ruta_logo_disco():
    """Ruta en disco de la marca, o None si falta.

    La devuelve opcional a propósito: un QR sin marca se sigue leyendo, así que
    un despliegue al que le falte el fichero debe imprimir etiquetas válidas en
    lugar de reventar la generación del PDF.
    """
    ruta = os.path.join(
        settings.BASE_DIR, "core", "static", *LOGO_ESTATICO.split("/")
    )
    return ruta if os.path.exists(ruta) else None


class Plano:
    """Geometría resuelta de un símbolo, en unidades de módulo.

    El origen está arriba a la izquierda, como la matriz del QR; cada
    renderizador la traslada a su propio sistema de coordenadas.
    """

    __slots__ = ("lado", "puntos", "ojos", "hueco")

    def __init__(self, lado, puntos, ojos, hueco):
        #: Lado total del símbolo en módulos, zona de silencio incluida.
        self.lado = lado
        #: Centros de los puntos de datos: [(cx, cy), ...].
        self.puntos = puntos
        #: Esquina superior izquierda de cada patrón de búsqueda: [(x, y), ...].
        self.ojos = ojos
        #: Hueco central de la marca: (x, y, lado).
        self.hueco = hueco


def plano(etiqueta) -> Plano:
    """Resuelve dónde va cada pieza del símbolo.

    Los patrones de búsqueda se apartan del flujo de puntos porque se dibujan
    como una sola figura —anillo redondeado más núcleo—, no como 49 módulos
    sueltos: es lo que les da la silueta reconocible del estilo.
    """
    codigo = segno.make(url_publica(etiqueta), error=NIVEL_CORRECCION)
    borde = ZONA_SILENCIO
    datos = codigo.symbol_size(border=0)[0]
    lado = datos + 2 * borde

    ojos = [
        (borde, borde),
        (borde + datos - OJO, borde),
        (borde, borde + datos - OJO),
    ]

    hueco_ini = (lado - HUECO_MODULOS) // 2
    hueco = (hueco_ini, hueco_ini, HUECO_MODULOS)

    def en_ojo(x, y):
        return any(ox <= x < ox + OJO and oy <= y < oy + OJO for ox, oy in ojos)

    def en_hueco(x, y):
        return hueco_ini <= x < hueco_ini + HUECO_MODULOS and (
            hueco_ini <= y < hueco_ini + HUECO_MODULOS
        )

    puntos = []
    for y, fila in enumerate(codigo.matrix_iter(border=borde)):
        for x, oscuro in enumerate(fila):
            if oscuro and not en_ojo(x, y) and not en_hueco(x, y):
                puntos.append((x + 0.5, y + 0.5))

    return Plano(lado, puntos, ojos, hueco)


def svg_en_linea(etiqueta, tamano_px=160) -> str:
    """SVG autocontenido con el estilo de puntos y la marca centrada.

    Generar al vuelo cuesta ~1 ms y es determinista. Guardar PNG en `/media`
    añadiría un volumen que respaldar y ficheros huérfanos a cambio de nada.

    La marca se referencia por su URL estática en lugar de incrustarse como
    data URI: el listado pinta hasta 30 códigos por página y treinta copias en
    base64 de la misma imagen pesarían más que la página entera.
    """
    p = plano(etiqueta)

    # El dibujo se hace en unidades de módulo y el viewBox lo escala al tamaño
    # pedido: así el mismo código sirve para 56 px en una tabla y para 300 px
    # en una ficha, sin recalcular nada.
    piezas = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {p.lado} {p.lado}" '
        f'width="{tamano_px}" height="{tamano_px}" role="img">'
    ]

    radio = DIAMETRO_PUNTO / 2
    for cx, cy in p.puntos:
        piezas.append(
            f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{radio:.3f}" fill="{AZUL}"/>'
        )

    for ox, oy in p.ojos:
        piezas.append(
            f'<rect x="{ox}" y="{oy}" width="{OJO}" height="{OJO}" '
            f'rx="{OJO_RADIO_ANILLO}" fill="{ROJO}"/>'
            f'<rect x="{ox + 1}" y="{oy + 1}" width="{OJO - 2}" height="{OJO - 2}" '
            f'rx="{max(0, OJO_RADIO_ANILLO - 1)}" fill="#ffffff"/>'
            f'<rect x="{ox + 2}" y="{oy + 2}" width="{OJO - 4}" height="{OJO - 4}" '
            f'rx="{OJO_RADIO_NUCLEO}" fill="{ROJO}"/>'
        )

    hx, hy, hlado = p.hueco
    marca = hlado * MARCA_EN_HUECO
    piezas.append(
        f'<image href="{static(LOGO_ESTATICO)}" '
        f'x="{hx + (hlado - marca) / 2:.2f}" y="{hy + (hlado - marca) / 2:.2f}" '
        f'width="{marca:.2f}" height="{marca:.2f}" '
        f'preserveAspectRatio="xMidYMid meet"/>'
    )

    piezas.append("</svg>")
    return "".join(piezas)
