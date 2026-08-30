"""Estáticos versionados por fecha de modificación.

`{% static %}` sirve la misma URL aunque el fichero cambie, y el servidor de
estáticos de `runserver` no manda `Cache-Control` — solo `Last-Modified` — así
que el navegador puede seguir usando una copia vieja de CSS/JS durante buen
rato sin que nadie note el porqué. Pasó varias veces seguidas depurando esta
misma app: el código ya estaba corregido, pero la pestaña seguía pintando la
hoja de estilos de antes del cambio.

`{% static_v %}` añade `?v=<mtime>` a la URL. Cambia el fichero, cambia el
número, cambia la URL: el navegador no tiene copia vieja que pueda reusar por
error, sin depender de que alguien se acuerde de recargar sin caché.
"""

import os
from functools import lru_cache
from pathlib import Path

from django import template
from django.apps import apps
from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static as _static

register = template.Library()


@register.simple_tag(name="static_v")
def static_v(path):
    return _versioned_static_url(path)


@lru_cache(maxsize=128)
def _versioned_static_url(path):
    """Resolve each static mtime once per process."""
    url = _static(path)

    ruta_disco = _find_static_file(path)
    if not ruta_disco and getattr(settings, "STATIC_ROOT", None):
        candidato = os.path.join(settings.STATIC_ROOT, path)
        if os.path.exists(candidato):
            ruta_disco = candidato

    if not ruta_disco:
        # Sin el fichero a mano (p. ej. un STATIC_ROOT que aún no existe en
        # este entorno) se sirve la URL tal cual: sin versión es mejor que
        # una excepción a mitad de render.
        return url

    version = int(os.path.getmtime(ruta_disco))
    separador = "&" if "?" in url else "?"
    return f"{url}{separador}v={version}"


def _find_static_file(path):
    """Find app static files without rebuilding Django's finder indexes."""
    for app_config in apps.get_app_configs():
        candidate = Path(app_config.path) / "static" / path
        if candidate.exists():
            return str(candidate)
    return finders.find(path)
