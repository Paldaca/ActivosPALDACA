"""
Despachador de los avisos de Activos que dependen del reloj.

Los avisos de hecho (alta, asignación) se emiten donde ocurre el cambio; aquí
solo vive la regla que nadie dispara en este repo:

- `usuario_inactivo_con_equipos`: un usuario puede desactivarse desde el panel
  de superadmin del Portal (no desde Activos — BR-USR-03 ya lo bloquea aquí si
  tiene equipos) sin que Activos tenga forma de enterarse en el momento. Corre
  una vez al día (08:00 hora local) y avisa a los admins de Activos sobre
  quienes siguen inactivos con equipo asignado. Cada usuario se avisa una sola
  vez por "episodio" (ver `AvisoUsuarioInactivo`): no repite el aviso cada día
  mientras nadie reasigne.

Pensado para una Scheduled Task de Coolify cada hora: la regla se autolimita a
su horario, así que corridas de más no duplican nada. Ver
docs/plan-notificaciones.md.

Uso:
    python manage.py enviar_notificaciones_activos
    python manage.py enviar_notificaciones_activos --dry-run
    python manage.py enviar_notificaciones_activos --regla usuario_inactivo_con_equipos --ahora
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from activos.services.avisos import (
    avisar_usuarios_inactivos_con_equipos,
    usuarios_inactivos_con_equipos,
)

# regla -> hora local (0-23) en que le toca correr.
HORARIOS = {
    "usuario_inactivo_con_equipos": 8,
}


class Command(BaseCommand):
    help = "Emite los avisos de Activos que dependen del reloj."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Cuenta a quién se avisaría, sin enviar nada al Portal.",
        )
        parser.add_argument(
            "--regla",
            choices=sorted(HORARIOS),
            help="Ejecuta solo esta regla.",
        )
        parser.add_argument(
            "--ahora",
            action="store_true",
            help="Ignora el horario y evalúa las reglas en este momento (pruebas).",
        )

    def handle(self, *args, **options):
        ahora = timezone.localtime()
        reglas = [options["regla"]] if options.get("regla") else sorted(HORARIOS)

        for regla in reglas:
            hora = HORARIOS[regla]
            if not options["ahora"] and ahora.hour != hora:
                continue
            self._ejecutar(regla, options["dry_run"])

    def _ejecutar(self, regla, dry_run):
        if dry_run:
            candidatos = usuarios_inactivos_con_equipos()
            self.stdout.write(
                f"[DRY-RUN] {regla}: se avisaría por {len(candidatos)} usuario(s) nuevo(s)."
            )
            return

        avisados = avisar_usuarios_inactivos_con_equipos()
        if avisados:
            self.stdout.write(
                self.style.SUCCESS(f"{regla}: aviso enviado por {avisados} usuario(s).")
            )
        else:
            self.stdout.write(
                f"{regla}: sin candidatos nuevos o el Portal no aceptó el aviso "
                "(ver logs NOTIFICACION_*)."
            )
