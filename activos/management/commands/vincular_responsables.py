"""Copia las asignaciones anteriores (cuenta del Portal) a empleados de Nomina.

La migracion 0012 ya lo hace una vez. Este comando es para volver a correrlo
despues de que RRHH vincule en Nomina las cuentas que faltaban, y para ver
que queda pendiente (condicion para la fase 2: eliminar `usuario_legacy`).

    python manage.py vincular_responsables
"""

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from activos.models import Activo, EmpleadoPortal
from activos.services.responsables import (
    tabla_empleados_disponible,
    vincular_responsables,
)


class Command(BaseCommand):
    help = "Vincula activos a empleados de Nomina y lista los que siguen pendientes."

    def handle(self, *args, **options):
        if not tabla_empleados_disponible():
            raise CommandError(
                "No existe la tabla portal_empleado: despliega el Portal, corre su "
                "migrate y pulsa «Sincronizar con el Portal» en Nomina."
            )
        if not EmpleadoPortal.objects.exists():
            raise CommandError(
                "portal_empleado esta vacia: pulsa «Sincronizar con el Portal» en "
                "Nomina (Empleados > Vinculos) antes de vincular."
            )

        vinculados = vincular_responsables(Activo, EmpleadoPortal)
        self.stdout.write(self.style.SUCCESS(f"Activos vinculados ahora: {vinculados}"))

        pendientes = (
            Activo.objects.filter(responsable__isnull=True, usuario_legacy__isnull=False)
            .values("usuario_legacy_id", "usuario_legacy__first_name",
                    "usuario_legacy__last_name", "usuario_legacy__username",
                    "usuario_legacy__email")
            .annotate(activos=Count("id"))
            .order_by("usuario_legacy__last_name")
        )
        if not pendientes:
            self.stdout.write(self.style.SUCCESS(
                "No queda ningun activo pendiente: ya se puede hacer la fase 2 "
                "(eliminar usuario_legacy)."
            ))
            return

        self.stdout.write(self.style.WARNING(
            f"\n{len(pendientes)} persona(s) con activos siguen sin empleado en Nomina. "
            "Vincula su cuenta en Nomina (Empleados > Vinculos, buscando por "
            "usuario o correo), sincroniza y vuelve a correr este comando:\n"
        ))
        self.stdout.write("portal_user_id;nombre;usuario;correo;activos")
        for p in pendientes:
            nombre = f"{p['usuario_legacy__first_name']} {p['usuario_legacy__last_name']}".strip()
            self.stdout.write(
                f"{p['usuario_legacy_id']};{nombre};{p['usuario_legacy__username']};"
                f"{p['usuario_legacy__email']};{p['activos']}"
            )
