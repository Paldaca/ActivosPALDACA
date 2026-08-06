"""Filtros compartidos entre listado, PDF y Excel."""

from django.db.models import Q

from activos.models import Activo


def filtros_desde_request(request) -> dict:
    """Extrae los filtros GET aplicados (para metadatos del reporte)."""
    claves = (
        "categoria",
        "subcategoria",
        "ubicacion",
        "estado",
        "asignacion",
        "usuario_asignado",
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
        "usuario_asignado",
    ).all()

    categoria_id = request.GET.get("categoria", "")
    subcategoria_id = request.GET.get("subcategoria", "")
    ubicacion_id = request.GET.get("ubicacion", "")
    estado = request.GET.get("estado", "")
    usuario_asignado_id = request.GET.get("usuario_asignado", "")
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
        queryset = queryset.filter(usuario_asignado__isnull=True)
    elif asignacion == "asignado":
        queryset = queryset.filter(usuario_asignado__isnull=False)
    if usuario_asignado_id:
        queryset = queryset.filter(usuario_asignado_id=usuario_asignado_id)
    if buscar:
        queryset = queryset.filter(
            Q(codigo_inventario__icontains=buscar)
            | Q(marca__icontains=buscar)
            | Q(modelo__icontains=buscar)
            | Q(numero_serial__icontains=buscar)
            | Q(usuario_asignado__first_name__icontains=buscar)
            | Q(usuario_asignado__last_name__icontains=buscar)
            | Q(ubicacion__nombre__icontains=buscar)
        )

    return queryset
