"""Personas = empleados de Nomina (tabla portal_empleado del Portal).

Solo consulta: los datos de un empleado (nombre, cargo, contacto, baja) se
gestionan en Nomina y llegan aqui sincronizados. Desde Activos solo se ve
quien responde por que equipo.
"""

from django.db.models import Count, Q
from django.views.generic import DetailView, ListView

from activos.decorators import AdminActivoRequiredMixin
from activos.models import Activo, EmpleadoPortal


def _empleados_gestion_queryset():
    return EmpleadoPortal.objects.annotate(
        num_activos=Count("activos_asignados", distinct=True)
    )


class UsuarioSearchView(AdminActivoRequiredMixin, ListView):
    """Buscador de empleados y de los equipos que tienen a cargo."""

    model = EmpleadoPortal
    template_name = "usuarios/usuario_search.html"
    context_object_name = "usuarios"
    paginate_by = 20

    def get_queryset(self):
        queryset = _empleados_gestion_queryset()

        estado = self.request.GET.get("estado", "activos")
        if estado == "activos":
            queryset = queryset.filter(activo=True)
        elif estado == "con_activos":
            queryset = queryset.filter(activo=True, num_activos__gt=0)
        elif estado == "sin_activos":
            queryset = queryset.filter(activo=True, num_activos=0)
        elif estado == "baja_con_activos":
            queryset = queryset.filter(activo=False, num_activos__gt=0)

        buscar = self.request.GET.get("buscar", "").strip()
        for palabra in buscar.split()[:5]:
            # Buscar por código de inventario responde a "¿de quién es PAL-LAP-007?"
            queryset = queryset.filter(
                Q(nombres__icontains=palabra)
                | Q(apellidos__icontains=palabra)
                | Q(cedula__icontains=palabra)
                | Q(cargo__icontains=palabra)
                | Q(email__icontains=palabra)
                | Q(activos_asignados__codigo_inventario__icontains=palabra)
            ).distinct()

        return queryset.order_by("apellidos", "nombres")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["buscar"] = self.request.GET.get("buscar", "")
        context["estado_actual"] = self.request.GET.get("estado", "activos")

        resumen = EmpleadoPortal.objects.aggregate(
            total=Count("id", filter=Q(activo=True), distinct=True),
            con_activos=Count(
                "id",
                filter=Q(activo=True, activos_asignados__isnull=False),
                distinct=True,
            ),
            baja_con_activos=Count(
                "id",
                filter=Q(activo=False, activos_asignados__isnull=False),
                distinct=True,
            ),
        )
        resumen["sin_activos"] = resumen["total"] - resumen["con_activos"]
        context["resumen"] = resumen
        # Fase 1 de la migracion: equipos aun asignados a una cuenta sin
        # empleado en Nomina (`python manage.py vincular_responsables`).
        context["pendientes_vincular"] = Activo.objects.filter(
            responsable__isnull=True, usuario_legacy__isnull=False
        ).count()
        return context


class UsuarioProfileView(AdminActivoRequiredMixin, DetailView):
    """Ficha del empleado con los activos bajo su responsabilidad."""

    model = EmpleadoPortal
    template_name = "usuarios/usuario_profile.html"
    context_object_name = "usuario"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        activos = list(self.object.activos_asignados.select_related(
            "subcategoria__categoria", "ubicacion"
        ).order_by(
            "subcategoria__categoria__nombre",
            "codigo_inventario",
        ))
        context["activos_asignados"] = activos
        context["total_activos"] = len(activos)
        context["en_mantenimiento"] = sum(
            activo.estado == "EM" for activo in activos
        )
        return context
