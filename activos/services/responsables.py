"""Fase 1 de la migracion a empleados de Nomina.

Convierte la asignacion anterior (`usuario_legacy`, una cuenta del Portal) en
`responsable` (un empleado de `portal_empleado`), buscando el empleado cuya
cuenta vinculada es esa. Lo que no tiene empleado se queda en `usuario_legacy`
y se lista como pendiente: RRHH lo resuelve vinculando la cuenta en Nomina, y
se vuelve a correr.
"""

from django.db import connection


def tabla_empleados_disponible(conexion=connection) -> bool:
    return "portal_empleado" in conexion.introspection.table_names()


def vincular_responsables(Activo, EmpleadoPortal):
    """Devuelve cuantos activos quedaron vinculados.

    Recibe los modelos para poder usarse igual desde la migracion (modelos
    historicos) que desde el comando. `update()` a proposito: no toca
    `fecha_actualizacion` ni dispara avisos, no es una reasignacion.
    """
    pendientes = Activo.objects.filter(
        responsable__isnull=True, usuario_legacy__isnull=False
    )
    usuarios = set(pendientes.values_list("usuario_legacy_id", flat=True))
    empleado_de = dict(
        EmpleadoPortal.objects.filter(usuario_id__in=usuarios).values_list("usuario_id", "pk")
    )
    vinculados = 0
    for usuario_id, empleado_id in empleado_de.items():
        vinculados += pendientes.filter(usuario_legacy_id=usuario_id).update(
            responsable_id=empleado_id, usuario_legacy_id=None
        )
    return vinculados
