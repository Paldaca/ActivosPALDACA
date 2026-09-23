"""
Despachador de los avisos de Activos que dependen del reloj.

Los avisos de hecho (alta, asignación, mantenimiento, baja) se emiten donde
ocurre el cambio; aquí solo viven las reglas que nadie dispara en este repo,
porque evalúan una condición que persiste en el tiempo, no un evento puntual:

- `usuario_inactivo_con_equipos` (diario, 08:00): un usuario puede
  desactivarse desde el panel de superadmin del Portal (no desde Activos —
  BR-USR-03 ya lo bloquea aquí si tiene equipos) sin que Activos tenga forma
  de enterarse en el momento.
- `etiqueta_sin_vincular` (diario, 09:00): una etiqueta QR impresa sigue en
  `PENDIENTE` más de `ACTIVOS_UMBRAL_ETIQUETA_SIN_VINCULAR_DIAS` días.
- `asignacion_sin_planilla` (diario, 10:00): una reasignación sigue sin
  planilla de entrega archivada más de
  `ACTIVOS_UMBRAL_ASIGNACION_SIN_PLANILLA_DIAS` días.
- `resumen_semanal_admins` (lunes, 08:00): altas, reasignaciones y
  mantenimientos de los últimos 7 días, en un solo aviso agregado. A
  diferencia de las tres anteriores, no necesita marcador de dedup propio:
  usa `clave_agrupacion` (una por semana) para que una segunda corrida en la
  misma ventana actualice el mismo aviso en vez de duplicarlo.

Las tres primeras corren una vez al día, no cada hora: la condición persiste
hasta que alguien actúa, así que un chequeo horario repetiría el aviso 24
veces sin que nada haya cambiado. Cada una se avisa una sola vez por
"episodio" (`AvisoUsuarioInactivo` / `AvisoPorUmbral`): el marcador se libera
solo cuando la condición deja de cumplirse, así que una recaída futura vuelve
a avisar.

`mantenimiento_estancado` queda deliberadamente fuera de este despachador por
ahora (sin implementar).

Pensado para una Scheduled Task de Coolify cada hora: cada regla se autolimita
a su horario (y, si aplica, su día), así que corridas de más no duplican
nada. Ver docs/plan-notificaciones.md y CRON_ENDPOINT.md.

Uso:
    python manage.py enviar_notificaciones_activos
    python manage.py enviar_notificaciones_activos --dry-run
    python manage.py enviar_notificaciones_activos --regla usuario_inactivo_con_equipos --ahora
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from activos.services.avisos import (
    asignaciones_sin_planilla,
    avisar_asignaciones_sin_planilla,
    avisar_etiquetas_sin_vincular,
    avisar_resumen_semanal_admins,
    avisar_usuarios_inactivos_con_equipos,
    etiquetas_sin_vincular,
    resumen_actividad_semanal,
    usuarios_inactivos_con_equipos,
)


def _candidatos_resumen_semanal():
    """Lista plana de los tres tipos de hecho, solo para contar en --dry-run."""
    resumen = resumen_actividad_semanal()
    return resumen["altas"] + resumen["reasignaciones"] + resumen["mantenimientos"]


# regla -> (dia de la semana 0=lunes..6=domingo o None para cualquier dia,
#           hora local, candidatos(), avisar(), unidad para el mensaje).
REGLAS = {
    "usuario_inactivo_con_equipos": (
        None,
        8,
        usuarios_inactivos_con_equipos,
        avisar_usuarios_inactivos_con_equipos,
        "usuario(s)",
    ),
    "etiqueta_sin_vincular": (
        None,
        9,
        etiquetas_sin_vincular,
        avisar_etiquetas_sin_vincular,
        "etiqueta(s)",
    ),
    "asignacion_sin_planilla": (
        None,
        10,
        asignaciones_sin_planilla,
        avisar_asignaciones_sin_planilla,
        "reasignación(es)",
    ),
    "resumen_semanal_admins": (
        0,
        8,
        _candidatos_resumen_semanal,
        avisar_resumen_semanal_admins,
        "hecho(s)",
    ),
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
            choices=sorted(REGLAS),
            help="Ejecuta solo esta regla.",
        )
        parser.add_argument(
            "--ahora",
            action="store_true",
            help="Ignora el horario (y el día) y evalúa las reglas en este momento (pruebas).",
        )

    def handle(self, *args, **options):
        ahora = timezone.localtime()
        reglas = [options["regla"]] if options.get("regla") else sorted(REGLAS)

        for regla in reglas:
            dia, hora, candidatos_fn, avisar_fn, unidad = REGLAS[regla]
            if not options["ahora"]:
                if ahora.hour != hora:
                    continue
                if dia is not None and ahora.weekday() != dia:
                    continue
            self._ejecutar(regla, candidatos_fn, avisar_fn, unidad, options["dry_run"])

    def _ejecutar(self, regla, candidatos_fn, avisar_fn, unidad, dry_run):
        if dry_run:
            candidatos = candidatos_fn()
            self.stdout.write(
                f"[DRY-RUN] {regla}: se avisaría por {len(candidatos)} {unidad} nuevo(s)."
            )
            return

        avisados = avisar_fn()
        if avisados:
            self.stdout.write(
                self.style.SUCCESS(f"{regla}: aviso enviado por {avisados} {unidad}.")
            )
        else:
            self.stdout.write(
                f"{regla}: sin candidatos nuevos o el Portal no aceptó el aviso "
                "(ver logs NOTIFICACION_*)."
            )
