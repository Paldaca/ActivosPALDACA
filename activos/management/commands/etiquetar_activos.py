"""Emite etiquetas QR para activos que ya están registrados.

La funcionalidad nació pensando en equipos que se compran a partir de ahora,
pero el inventario existente también necesita adhesivos. Aquí la etiqueta se
crea al revés: en lugar de apartar un código nuevo y esperar a que aparezca el
activo, se toma el código que el activo YA tiene y se ata en el mismo acto.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from activos.models import Activo, EtiquetaQR


class Command(BaseCommand):
    help = "Crea etiquetas QR para activos ya registrados que aún no tienen una."

    def add_arguments(self, parser):
        parser.add_argument(
            "--subcategoria",
            dest="prefijo",
            help="Limita a una subcategoría por su prefijo (ej. LAP).",
        )
        parser.add_argument(
            "--limite",
            type=int,
            help="Procesa como mucho N activos.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra qué se haría, sin escribir nada.",
        )

    def handle(self, *args, **opciones):
        pendientes = (
            Activo.objects.select_related("subcategoria")
            # `etiquetas` incluye las anuladas a propósito: un activo cuyo
            # adhesivo se estropeó se reetiqueta a mano desde la interfaz, no
            # en una pasada masiva que podría reimprimirle una etiqueta que
            # alguien acaba de retirar por un motivo.
            .filter(etiquetas__isnull=True)
            .order_by("codigo_inventario")
        )

        prefijo = (opciones.get("prefijo") or "").strip().upper()
        if prefijo:
            pendientes = pendientes.filter(subcategoria__prefijo=prefijo)
            if not pendientes.exists():
                raise CommandError(
                    f"No hay activos sin etiqueta con el prefijo {prefijo!r}."
                )

        limite = opciones.get("limite")
        if limite:
            pendientes = pendientes[:limite]

        activos = list(pendientes)
        if not activos:
            self.stdout.write(self.style.SUCCESS("Todos los activos ya tienen etiqueta."))
            return

        if opciones["dry_run"]:
            for activo in activos:
                self.stdout.write(f"  [dry-run] {activo.codigo_inventario}")
            self.stdout.write(
                self.style.WARNING(f"\n{len(activos)} etiqueta(s) se crearían.")
            )
            return

        ahora = timezone.now()
        codigos = [activo.codigo_inventario for activo in activos]
        with transaction.atomic():
            EtiquetaQR.objects.bulk_create([
                EtiquetaQR(
                    # Sin reservar nada: el código ya existe y es de este activo.
                    codigo_reservado=activo.codigo_inventario,
                    subcategoria=activo.subcategoria,
                    activo=activo,
                    estado=EtiquetaQR.EstadoEtiqueta.VINCULADA,
                    fecha_vinculacion=ahora,
                    # `bulk_create` no pasa por save(), así que el token va explícito.
                    token=EtiquetaQR.generar_token(),
                )
                for activo in activos
            ])
            # Relectura para obtener las claves primarias: MySQL no las
            # devuelve en un bulk_create, y sin ellas el enlace de impresión
            # que se imprime abajo saldría vacío.
            etiquetas = list(
                EtiquetaQR.objects.filter(codigo_reservado__in=codigos)
                .order_by("codigo_reservado")
            )

        self.stdout.write(
            self.style.SUCCESS(f"{len(etiquetas)} etiqueta(s) creada(s).")
        )
        ids = ",".join(str(e.pk) for e in etiquetas)
        self.stdout.write(f"\nPara imprimirlas:\n  /reportes/etiquetas/?ids={ids}")
