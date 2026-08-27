"""Tags para incrustar el QR de una etiqueta dentro de una plantilla."""

from django import template
from django.utils.safestring import mark_safe

from activos.services.qr import svg_en_linea

register = template.Library()


@register.simple_tag(name="qr_svg")
def qr_svg(etiqueta, tamano=110):
    """SVG del QR, en línea. Uso: {% qr_svg etiqueta 90 %}

    Va marcado como seguro porque lo genera `segno` a partir de una URL que
    construye el propio servidor: no hay entrada del usuario en el texto
    codificado, solo el token que generó el sistema.
    """
    return mark_safe(svg_en_linea(etiqueta, tamano_px=tamano))
