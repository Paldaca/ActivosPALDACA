"""Comprueba que la tabla `portal_empleado` del Portal tiene las columnas que espera Activos.

    python manage.py verificar_portal_empleado

Sale con error si falta alguna: el Portal cambio el esquema de un dato maestro
sin avisar (contrato: solo se pueden añadir columnas). Se ejecuta en cada
arranque del contenedor (docker-entrypoint.sh) sin bloquearlo: un aviso claro
en el log vale mas que un despliegue que no levanta por un cambio ajeno.
"""

from django.core.management.base import BaseCommand, CommandError

from activos.services.contrato_portal import columnas_faltantes


class Command(BaseCommand):
    help = "Verifica el contrato de esquema con la tabla portal_empleado del Portal."

    def handle(self, *args, **options):
        faltantes = columnas_faltantes()
        if faltantes is None:
            raise CommandError(
                "No existe la tabla portal_empleado: el Portal aun no ha desplegado y "
                "migrado. Hasta entonces, el responsable de los activos no se puede leer."
            )
        if faltantes:
            raise CommandError(
                "portal_empleado ya no tiene las columnas que espera Activos: "
                + ", ".join(faltantes)
                + ". El Portal rompio el contrato de datos maestros (solo se pueden "
                "añadir columnas). Avisar al Portal antes de seguir; no migrar aqui."
            )
        self.stdout.write(self.style.SUCCESS("portal_empleado cumple el contrato."))
