"""Filtros compartidos entre listado, PDF y Excel."""

from django.db.models import Q

from activos.models import SIN_RESPONSABLE, Activo


def filtros_desde_request(request) -> dict:
    """Extrae los filtros GET aplicados (para metadatos del reporte)."""
    claves = (
        "categoria",
        "subcategoria",
        "ubicacion",
        "estado",
        "asignacion",
        "responsable",
        "buscar",
    )
    return {k: request.GET.get(k) for k in claves if request.GET.get(k)}


def queryset_activos_filtrados(request):
    """
    Misma lógica de filtros que el listado de activos.
    PDF y Excel deben reflejar exactamente lo que el usuario ve.
    """
    queryset = Activo.objects.select_related(
        "subcategoria__categoria",
        "ubicacion",
        "responsable",
        "usuario_legacy",
    ).all()

    categoria_id = request.GET.get("categoria", "")
    subcategoria_id = request.GET.get("subcategoria", "")
    ubicacion_id = request.GET.get("ubicacion", "")
    estado = request.GET.get("estado", "")
    responsable_id = request.GET.get("responsable", "")
    buscar = request.GET.get("buscar", "")
    asignacion = request.GET.get("asignacion", "")

    if categoria_id:
        queryset = queryset.filter(subcategoria__categoria_id=categoria_id)
    if subcategoria_id:
        queryset = queryset.filter(subcategoria_id=subcategoria_id)
    if ubicacion_id:
        queryset = queryset.filter(ubicacion_id=ubicacion_id)
    if estado:
        queryset = queryset.filter(estado=estado)
    if asignacion == "libre":
        queryset = queryset.filter(SIN_RESPONSABLE)
    elif asignacion == "asignado":
        queryset = queryset.exclude(SIN_RESPONSABLE)
    if responsable_id:
        queryset = queryset.filter(responsable_id=responsable_id)
    if buscar:
        queryset = queryset.filter(
            Q(codigo_inventario__icontains=buscar)
            | Q(marca__icontains=buscar)
            | Q(modelo__icontains=buscar)
            | Q(numero_serial__icontains=buscar)
            | Q(responsable__nombres__icontains=buscar)
            | Q(responsable__apellidos__icontains=buscar)
            | Q(responsable__cedula__icontains=buscar)
            | Q(usuario_legacy__first_name__icontains=buscar)
            | Q(usuario_legacy__last_name__icontains=buscar)
            | Q(ubicacion__nombre__icontains=buscar)
        )

    return queryset
