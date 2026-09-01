"""Servicios de dominio del módulo de Activos.

Lógica que no pertenece ni al modelo (porque coordina varias tablas) ni a la
vista (porque no depende del request). Se importa desde ambos.
"""

from .codigos import reservar_codigos, siguiente_codigo
from .etiquetas import crear_etiqueta_vinculada_para_activo
from .qr import codigo_inventario_etiqueta, plano, svg_en_linea, url_publica

__all__ = [
    "codigo_inventario_etiqueta",
    "crear_etiqueta_vinculada_para_activo",
    "plano",
    "reservar_codigos",
    "siguiente_codigo",
    "svg_en_linea",
    "url_publica",
]
