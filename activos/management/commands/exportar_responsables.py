"""Exporta a CSV las personas que hoy son responsables de algun activo.

Paso 1 de la auditoria previa al cambio "personas asignables = empleados de
Nomina". El CSV se cruza despues en Nomina con `auditar_responsables_activos`
(las dos BD estan separadas: no hay JOIN posible). Solo lectura.

    python manage.py exportar_responsables > responsables.csv
"""

import csv
import sys

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db.models import Count


class Command(BaseCommand):
    help = "CSV de personas con activos asignados (id de core_usuario, nombre, correo, cantidad)."

    def handle(self, *args, **options):
        personas = (
            get_user_model()
            .objects.filter(activos_asignados__isnull=False)
            .annotate(num_activos=Count("activos_asignados"))
            .order_by("last_name", "first_name")
        )
        escritor = csv.writer(sys.stdout, lineterminator="\n")
        escritor.writerow(["portal_user_id", "nombre", "username", "email", "is_active", "num_activos"])
        for p in personas:
            escritor.writerow([
                p.pk,
                p.get_full_name().strip() or p.username,
                p.username,
                p.email,
                int(p.is_active),
                p.num_activos,
            ])
