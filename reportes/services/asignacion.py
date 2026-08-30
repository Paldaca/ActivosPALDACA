"""Planilla de asignación de equipos: render bajo demanda."""

from datetime import datetime

from django.http import HttpResponse
from django.templatetags.static import static
from django.utils import timezone

from .html_pdf import render_html_pdf
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


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def exportar_asignacion_pdf(
    activos,
    entrega_usuario,
    observaciones="",
) -> HttpResponse:
    """Download an N-page PDF (one planilla per asset)."""
    context = contexto_planilla(activos, entrega_usuario, observaciones)
    filename = f"planilla_asignacion_{_timestamp()}.pdf"
    return render_html_pdf(PLANTILLA, context, filename)
