"""Servicios de dominio del módulo de Activos.

Lógica que no pertenece ni al modelo (porque coordina varias tablas) ni a la
vista (porque no depende del request). Se importa desde ambos.
"""

from .codigos import reservar_codigos, siguiente_codigo
from .qr import lado_en_modulos, matriz, svg_en_linea, url_publica

__all__ = [
    "lado_en_modulos",
    "matriz",
    "reservar_codigos",
    "siguiente_codigo",
    "svg_en_linea",
    "url_publica",
]
