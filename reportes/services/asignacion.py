"""Planilla de asignación de equipos: render, guardar y descargar."""

import re
from datetime import datetime

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import HttpResponse
from django.templatetags.static import static
from django.utils import timezone

from activos.models import Activo, HistorialMovimiento

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


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _ruta_planilla(activo) -> str:
    stamp = timezone.now().strftime("%Y%m%d_%H%M%S_%f")
    codigo = re.sub(
        r"[^A-Z0-9._-]",
        "_",
        (activo.codigo_inventario or "ACTIVO").upper(),
    )
    return f"planillas/{codigo}_{stamp}.pdf"


def _activo_con_relaciones(activo) -> Activo:
    return Activo.objects.select_related(
        "subcategoria__categoria",
        "ubicacion",
        "usuario_asignado__disciplina",
    ).get(pk=activo.pk)


def _usuario_para_historial(entrega_usuario):
    if entrega_usuario is None:
        return None
    if getattr(entrega_usuario, "is_authenticated", True):
        return entrega_usuario
    return None


def guardar_planilla(
    activo,
    entrega_usuario,
    observaciones="",
    movimiento=None,
):
    """Render one planilla, store as current file, attach to history."""
    activo = _activo_con_relaciones(activo)
    if not activo.usuario_asignado_id:
        raise ValueError("El activo no tiene responsable.")
    pdf_bytes = render_html_pdf_bytes(
        PLANTILLA,
        contexto_planilla([activo], entrega_usuario, observaciones),
    )
    rel = default_storage.save(
        _ruta_planilla(activo),
        ContentFile(pdf_bytes),
    )
    Activo.objects.filter(pk=activo.pk).update(
        planilla_pdf=rel,
        planilla_generada_en=timezone.now(),
    )
    if movimiento is None:
        movimiento = HistorialMovimiento.objects.create(
            activo=activo,
            tipo_movimiento=HistorialMovimiento.TipoMovimiento.PLANILLA,
            descripcion="Planilla de asignación generada.",
            campo_modificado="planilla_pdf",
            usuario=_usuario_para_historial(entrega_usuario),
        )
    HistorialMovimiento.objects.filter(pk=movimiento.pk).update(
        archivo_planilla=rel,
    )
    activo.planilla_pdf = rel
    return rel


def limpiar_planilla_vigente(activo):
    """Clear the current planilla pointer without deleting history files."""
    Activo.objects.filter(pk=activo.pk).update(
        planilla_pdf="",
        planilla_generada_en=None,
    )
    activo.planilla_pdf = ""
    activo.planilla_generada_en = None


def exportar_asignacion_pdf(
    activos,
    entrega_usuario,
    observaciones="",
) -> HttpResponse:
    """Download an N-page PDF (one planilla per asset)."""
    context = contexto_planilla(activos, entrega_usuario, observaciones)
    filename = f"planilla_asignacion_{_timestamp()}.pdf"
    return render_html_pdf(PLANTILLA, context, filename)
