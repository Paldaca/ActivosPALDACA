"""API de alto nivel para las vistas de reportes."""

from datetime import datetime

from django.http import HttpResponse
from django.utils import timezone

from activos.models import Activo

from .excel import exportar_activos_excel
from .filtros import filtros_desde_request, queryset_activos_filtrados
from .pdf import formatear_fecha, generar_pdf


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def exportar_inventario_pdf(request) -> HttpResponse:
    filtros = filtros_desde_request(request)
    activos = list(queryset_activos_filtrados(request))
    context = {
        "activos": activos,
        "fecha_generacion": formatear_fecha(timezone.now().date()),
        "filtros_aplicados": (
            ", ".join(f"{k}: {v}" for k, v in filtros.items()) if filtros else None
        ),
    }
    return generar_pdf(
        "reportes/reporte_activos.html",
        context,
        f"reporte_activos_{_timestamp()}.pdf",
    )


def exportar_inventario_excel(request) -> HttpResponse:
    filtros = filtros_desde_request(request)
    activos = list(queryset_activos_filtrados(request))
    return exportar_activos_excel(
        activos,
        f"activos_{_timestamp()}.xlsx",
        filtros_aplicados=filtros,
    )


def exportar_nota_entrega_pdf(
    *,
    activos_ids: list,
    responsable_entrega: str = "",
    observaciones: str = "",
) -> HttpResponse:
    activos = list(
        Activo.objects.select_related(
            "subcategoria__categoria",
            "ubicacion",
            "usuario_asignado",
        ).filter(id__in=activos_ids)
    )
    context = {
        "activos": activos,
        "fecha_entrega": formatear_fecha(timezone.now().date()),
        "responsable_entrega": responsable_entrega,
        "observaciones": observaciones,
    }
    return generar_pdf(
        "reportes/nota_entrega.html",
        context,
        f"nota_entrega_{_timestamp()}.pdf",
    )
