"""Generación de códigos QR para las etiquetas de activos.

Único punto donde se decide qué se codifica y con qué parámetros. Aislarlo
importa porque los parámetros están atados a una restricción física —el
adhesivo Avery 5160 mide 66,7 × 25,4 mm— y conviene poder recalibrarlos en un
sitio tras imprimir pruebas reales, no repartidos entre plantillas y PDF.

Aquí NO se lee ningún QR: el escaneo lo hace la cámara del teléfono. Por eso no
entra ninguna dependencia de visión por computadora (`opencv`, `pyzbar`), que
en `python:3.13-slim` arrastraría librerías del sistema.
"""

from urllib.parse import urljoin

import segno
from django.conf import settings
from django.urls import reverse

#: Corrección de errores. 'Q' (25 %) y no 'M' (15 %) porque estos adhesivos se
#: rayan, se ensucian y viven pegados a equipos que se mueven.
NIVEL_CORRECCION = "q"

#: Zona de silencio en módulos. El estándar pide 4; a 22 mm de lado eso se come
#: demasiada superficie útil, y el blanco del propio adhesivo aporta el margen
#: óptico que falta. Verificar con impresión real antes de bajar de 2.
ZONA_SILENCIO = 2


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


def _codigo(etiqueta):
    return segno.make(url_publica(etiqueta), error=NIVEL_CORRECCION)


def svg_en_linea(etiqueta, tamano_px=160) -> str:
    """SVG listo para incrustar en una plantilla, sin servir ningún fichero.

    Generar al vuelo cuesta ~1 ms y es determinista. Guardar PNG en `/media`
    añadiría un volumen que respaldar y ficheros huérfanos a cambio de nada.
    """
    escala = max(1, round(tamano_px / (_codigo(etiqueta).symbol_size(border=ZONA_SILENCIO)[0])))
    return _codigo(etiqueta).svg_inline(
        scale=escala,
        border=ZONA_SILENCIO,
        dark="#000000",
    )


def matriz(etiqueta):
    """Filas de booleanos del símbolo, incluida la zona de silencio.

    Se expone en crudo para que el generador del PDF dibuje los módulos como
    rectángulos de ReportLab y controle el tamaño en milímetros exactos, en
    lugar de escalar una imagen y arriesgar bordes difuminados al imprimir.
    """
    return [
        list(fila)
        for fila in _codigo(etiqueta).matrix_iter(border=ZONA_SILENCIO)
    ]


def lado_en_modulos(etiqueta) -> int:
    """Cuántos módulos de ancho tiene el símbolo con su zona de silencio."""
    return _codigo(etiqueta).symbol_size(border=ZONA_SILENCIO)[0]
