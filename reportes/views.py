import os

from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect

from activos.decorators import requiere_modulo_paldaca
from activos.models import Activo, EtiquetaQR, HistorialMovimiento

from .services import (
    exportar_inventario_excel,
    exportar_inventario_pdf,
    generar_hoja_etiquetas,
)
from .services.asignacion import (
    exportar_asignacion_pdf,
    guardar_planilla,
)


def _ids_desde_request(request):
    """Parse asset ids from POST checkboxes or GET `activos`."""
    if request.method == "POST":
        crudos = request.POST.getlist("activos_seleccionados")
        if not crudos:
            crudos = (request.POST.get("activos") or "").split(",")
    else:
        crudos = (request.GET.get("activos") or "").split(",")
    ids = []
    vistos = set()
    for trozo in crudos:
        trozo = str(trozo).strip()
        if not trozo.isdigit():
            continue
        pk = int(trozo)
        if pk in vistos:
            continue
        vistos.add(pk)
        ids.append(pk)
    return ids


def _activos_para_planilla(ids):
    encontrados = Activo.objects.select_related(
        "subcategoria__categoria",
        "ubicacion",
        "usuario_asignado__disciplina",
    ).filter(pk__in=ids)
    por_id = {activo.pk: activo for activo in encontrados}
    return [por_id[pk] for pk in ids if pk in por_id]


def _error_entrega(activos):
    if not activos:
        return "Debe seleccionar al menos un activo."
    responsables = {a.usuario_asignado_id for a in activos}
    if None in responsables:
        return (
            "Hay equipos sin responsable; no hay quien reciba la planilla."
        )
    if len(responsables) > 1:
        return "La planilla es de una entrega a una sola persona."
    return None


def _redirect_planilla(ids):
    if len(ids) == 1:
        return redirect("activos:activo-detail", pk=ids[0])
    return redirect("activos:activo-list")


def _respuesta_archivo_pdf(campo, nombre):
    if not campo:
        raise Http404("No hay planilla guardada.")
    try:
        handle = campo.open("rb")
    except FileNotFoundError as exc:
        raise Http404("El archivo de la planilla ya no está.") from exc
    base = os.path.basename(campo.name) or nombre
    return FileResponse(
        handle,
        as_attachment=True,
        filename=base,
        content_type="application/pdf",
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
    """Compatibilidad: la nota de entrega ahora es la planilla."""
    return constancia_asignacion(request)


@requiere_modulo_paldaca
def constancia_asignacion(request):
    """GET prints; POST also saves the current planilla of each asset."""
    ids = _ids_desde_request(request)
    if not ids:
        messages.error(
            request,
            "Debe seleccionar al menos un activo para la planilla.",
        )
        return redirect("activos:activo-list")

    activos = _activos_para_planilla(ids)
    error = _error_entrega(activos)
    if error:
        messages.error(request, error)
        return _redirect_planilla(ids)

    observaciones = ""
    if request.method == "POST":
        observaciones = (request.POST.get("observaciones") or "").strip()
        try:
            for activo in activos:
                guardar_planilla(
                    activo,
                    entrega_usuario=request.user,
                    observaciones=observaciones,
                )
        except Exception as exc:
            messages.error(request, f"Error al guardar la planilla: {exc}")
            return _redirect_planilla(ids)

    try:
        return exportar_asignacion_pdf(
            activos,
            entrega_usuario=request.user,
            observaciones=observaciones,
        )
    except Exception as exc:
        messages.error(request, f"Error al generar la planilla: {exc}")
        return _redirect_planilla(ids)


@requiere_modulo_paldaca
def descargar_planilla_vigente(request, pk):
    """Serve the current planilla stored on the asset."""
    activo = get_object_or_404(Activo, pk=pk)
    if not activo.planilla_pdf:
        messages.error(request, "Este equipo aún no tiene planilla vigente.")
        return redirect("activos:activo-detail", pk=pk)
    return _respuesta_archivo_pdf(
        activo.planilla_pdf,
        f"planilla_{activo.codigo_inventario}.pdf",
    )


@requiere_modulo_paldaca
def descargar_planilla_historial(request, pk):
    """Serve the planilla snapshot attached to a movement."""
    movimiento = get_object_or_404(
        HistorialMovimiento.objects.select_related("activo"),
        pk=pk,
    )
    return _respuesta_archivo_pdf(
        movimiento.archivo_planilla,
        f"planilla_{movimiento.activo.codigo_inventario}.pdf",
    )


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
