"""Planilla de asignación: render bajo demanda y copia en historial."""

import re
import unicodedata

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import HttpResponse
from django.templatetags.static import static
from django.utils import timezone

from activos.models import Activo

from .html_pdf import render_html_pdf, render_html_pdf_bytes
from .pdf import formatear_fecha

PLANTILLA = "reportes/asignacion_activos.html"


def datos_persona(usuario) -> dict:
    """Name, role, contact. Cedula stays None until core_usuario has it."""
    if not usuario:
        return {
            "nombre": "",
            "cargo": "",
            "telefono": "",
            "email": "",
            "cedula": None,
        }
    nombre = f"{usuario.first_name or ''} {usuario.last_name or ''}"
    nombre = nombre.strip()
    cargo = ""
    disciplina = getattr(usuario, "disciplina", None)
    if disciplina is not None:
        cargo = disciplina.nombre
    return {
        "nombre": nombre or (usuario.email or usuario.username),
        "cargo": cargo,
        "telefono": getattr(usuario, "telefono", None) or "",
        "email": usuario.email or "",
        "cedula": None,
    }


def contexto_planilla(activos, entrega_usuario, observaciones=""):
    """Build the template context for one or more planilla pages."""
    recibe = None
    if activos:
        recibe = activos[0].usuario_asignado
    return {
        "activos": activos,
        "entrega": datos_persona(entrega_usuario),
        "recibe": datos_persona(recibe),
        "fecha": formatear_fecha(timezone.now().date()),
        "observaciones": (observaciones or "").strip(),
        "logo_url": static("core/img/logo_paldaca.png"),
    }


def _slug(texto: str) -> str:
    """ASCII, filename-safe slug: 'Juan Pérez' -> 'juan_perez'."""
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = texto.encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^A-Za-z0-9]+", "_", texto).strip("_").lower()
    return texto


def _ruta_planilla_historial(activo) -> str:
    stamp = timezone.now().strftime("%Y%m%d_%H%M%S_%f")
    codigo = re.sub(
        r"[^A-Z0-9._-]",
        "_",
        (activo.codigo_inventario or "ACTIVO").upper(),
    )
    return f"planillas/historial/{codigo}_{stamp}.pdf"


def _activo_con_relaciones(activo) -> Activo:
    return Activo.objects.select_related(
        "subcategoria__categoria",
        "ubicacion",
        "usuario_asignado__disciplina",
    ).get(pk=activo.pk)


def guardar_planilla_en_historial(
    activo,
    entrega_usuario,
    movimiento,
    observaciones="",
):
    """Render one planilla and attach it to a history movement."""
    if movimiento is None:
        return None
    activo = _activo_con_relaciones(activo)
    if not activo.usuario_asignado_id:
        return None
    pdf_bytes = render_html_pdf_bytes(
        PLANTILLA,
        contexto_planilla([activo], entrega_usuario, observaciones),
    )
    rel = default_storage.save(
        _ruta_planilla_historial(activo),
        ContentFile(pdf_bytes),
    )
    movimiento.archivo_planilla = rel
    movimiento.save(update_fields=["archivo_planilla"])
    return rel


def exportar_asignacion_pdf(
    activos,
    entrega_usuario,
    observaciones="",
) -> HttpResponse:
    """Download a single-page PDF listing every asset for one user."""
    context = contexto_planilla(activos, entrega_usuario, observaciones)
    nombre = _slug(context["recibe"]["nombre"]) or "sin_asignar"
    fecha = timezone.now().strftime("%Y%m%d")
    filename = f"planilla_{nombre}_{fecha}.pdf"
    return render_html_pdf(PLANTILLA, context, filename, inline=True)
