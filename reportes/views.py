from django.contrib import messages
from django.shortcuts import redirect

from activos.decorators import requiere_modulo_paldaca

from activos.models import EtiquetaQR

from .services import (
    exportar_inventario_excel,
    exportar_inventario_pdf,
    exportar_nota_entrega_pdf,
    generar_hoja_etiquetas,
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


@requiere_modulo_paldaca
def imprimir_etiquetas(request):
    """Hoja Avery 5160 con las etiquetas cuyos ids llegan en `?ids=1,2,3`."""
    crudos = (request.GET.get("ids") or "").strip()
    ids = [trozo for trozo in crudos.split(",") if trozo.isdigit()]
    if not ids:
        messages.error(request, "No indicaste qué etiquetas imprimir.")
        return redirect("activos:etiqueta-list")

    etiquetas = list(
        EtiquetaQR.objects.select_related("subcategoria__categoria")
        .filter(pk__in=ids)
        .exclude(estado=EtiquetaQR.EstadoEtiqueta.ANULADA)
        .order_by("codigo_reservado")
    )
    if not etiquetas:
        messages.error(
            request,
            "Esas etiquetas ya no existen o están anuladas.",
        )
        return redirect("activos:etiqueta-list")

    try:
        return generar_hoja_etiquetas(etiquetas)
    except Exception as e:
        messages.error(request, f"Error al generar las etiquetas: {e}")
        return redirect("activos:etiqueta-list")
