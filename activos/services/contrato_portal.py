"""Comprobacion del contrato de esquema con `portal_empleado` (dato maestro del Portal).

`EmpleadoPortal` es una copia MANUAL, `managed = False`, de una tabla que crea y
migra el Portal (Portal-Paldaca/backend/portal/models.py). Si el Portal
renombrara o quitara una columna, Activos fallaria en tiempo de ejecucion, no en
un test. El Portal se compromete a solo AÑADIR columnas (Portal-Paldaca/docs/
PALDACA_SUITE/CONTRATO_DATOS_MAESTROS.md §5) y lo vigila en sus propios tests;
esto es la otra mitad: comprobar, contra la tabla REAL, que sigue teniendo
todo lo que este modelo espera.

Los tests de Activos no pueden hacerlo: `conftest.py` crea la tabla a partir del
propio modelo, asi que compararlos entre si siempre pasaria.
"""

from django.db import connection

from activos.models import EmpleadoPortal


def columnas_esperadas() -> set[str]:
    return {campo.column for campo in EmpleadoPortal._meta.concrete_fields}


def columnas_faltantes(conexion=connection, tabla: str | None = None):
    """Columnas que el modelo espera y la tabla no tiene (ordenadas).

    Devuelve `None` si la tabla no existe (el Portal aun no desplego su
    migracion): no es lo mismo que "faltan columnas".
    """
    tabla = tabla or EmpleadoPortal._meta.db_table
    if tabla not in conexion.introspection.table_names():
        return None
    with conexion.cursor() as cursor:
        reales = {c.name for c in conexion.introspection.get_table_description(cursor, tabla)}
    return sorted(columnas_esperadas() - reales)
