from django.contrib import messages
from django.shortcuts import redirect

from activos.decorators import requiere_modulo_paldaca

from .services import (
    exportar_inventario_excel,
    exportar_inventario_pdf,
    exportar_nota_entrega_pdf,
)


@requiere_modulo_paldaca
def generar_reporte_activos(request):
    """PDF del inventario filtrado (template reportes/reporte_activos.html)."""
    try:
        return exportar_inventario_pdf(request)
    except Exception as e:
        messages.error(request, f"Error al generar el reporte: {e}")
        return redirect("activos:activo-list")


@requiere_modulo_paldaca
def exportar_activos_excel(request):
    """Excel del inventario con los mismos filtros del listado."""
    try:
        return exportar_inventario_excel(request)
    except Exception as e:
        messages.error(request, f"Error al exportar Excel: {e}")
        return redirect("activos:activo-list")


@requiere_modulo_paldaca
def generar_nota_entrega(request):
    """PDF de nota de entrega (template reportes/nota_entrega.html)."""
    try:
        activos_ids = request.POST.getlist("activos_seleccionados")
        if not activos_ids:
            messages.error(
                request,
                "Debe seleccionar al menos un activo para generar la nota de entrega.",
            )
            return redirect("activos:activo-list")

        return exportar_nota_entrega_pdf(
            activos_ids=activos_ids,
            responsable_entrega=request.POST.get("responsable_entrega", ""),
            observaciones=request.POST.get("observaciones", ""),
        )
    except Exception as e:
        messages.error(request, f"Error al generar la nota de entrega: {e}")
        return redirect("activos:activo-list")
