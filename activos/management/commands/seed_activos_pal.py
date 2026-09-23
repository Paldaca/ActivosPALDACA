"""
Carga datos de ejemplo de activos con códigos PAL-<ABREV>-NNN
(ej.: PAL-D-001 desktop, PAL-L-001 laptop, PAL-M-001 monitor, PAL-MO-001 mouse).
Reparte los activos entre los empleados activos de Nómina (tabla
portal_empleado); si no hay ninguno sincronizado, quedan sin asignar.

Uso:
  python manage.py seed_activos_pal
  python manage.py seed_activos_pal --por-tipo 5 --dry-run
"""
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from activos.forms import empleados_asignables
from activos.models import Activo, Categoria, SubCategoria, Ubicacion


def maximo_sufijo_codigo_pal(abreviatura: str) -> int:
    """Mayor sufijo numérico N en códigos PAL-ABREV-NNN ya existentes (0 si no hay)."""
    abr = abreviatura.strip().upper()
    prefix = f"PAL-{abr}-"
    patron = re.compile(rf"^PAL-{re.escape(abr)}-(\d+)$", re.IGNORECASE)
    max_n = 0
    for codigo in Activo.objects.filter(codigo_inventario__istartswith=prefix).values_list(
        "codigo_inventario", flat=True
    ):
        m = patron.match((codigo or "").strip())
        if m:
            max_n = max(max_n, int(m.group(1)))
    return max_n


def codigo_inventario_pal(abreviatura: str, numero: int) -> str:
    abr = abreviatura.strip().upper()
    return f"PAL-{abr}-{numero:03d}"


DEFINICIONES_TIPOS = [
    {"abbr": "D", "subcategoria": "PC de escritorio (Desktop)", "marca": "HP", "modelo": "ProDesk 400 G7"},
    {"abbr": "L", "subcategoria": "Laptop", "marca": "Lenovo", "modelo": "ThinkPad E14 Gen 5"},
    {"abbr": "M", "subcategoria": "Monitor", "marca": "Samsung", "modelo": 'F24T350FHU 24"'},
    {"abbr": "MO", "subcategoria": "Mouse", "marca": "Logitech", "modelo": "M185"},
]


class Command(BaseCommand):
    help = (
        "Inserta activos de ejemplo (desktop D, laptop L, monitor M, mouse MO) "
        "con códigos PAL-<abreviatura>-001, 002, ...; los reparte en round-robin "
        "entre los empleados activos de Nómina."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--por-tipo",
            type=int,
            default=3,
            help="Cantidad de activos a crear por cada tipo (default: 3).",
        )
        parser.add_argument(
            "--categoria",
            type=str,
            default="Equipos de cómputo y periféricos",
            help="Nombre de la categoría padre (se crea si no existe).",
        )
        parser.add_argument(
            "--ubicacion",
            type=str,
            default="Almacén general",
            help="Nombre de la ubicación (se crea si no existe).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Solo muestra qué se crearía, sin escribir en la base de datos.",
        )

    def handle(self, *args, **options):
        por_tipo = options["por_tipo"]
        if por_tipo < 1:
            self.stderr.write(self.style.ERROR("--por-tipo debe ser >= 1"))
            return

        categoria_nombre = options["categoria"]
        ubicacion_nombre = options["ubicacion"]
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("Modo dry-run: no se guardará nada."))

        def run():
            categoria, _ = Categoria.objects.get_or_create(nombre=categoria_nombre)
            ubicacion, _ = Ubicacion.objects.get_or_create(nombre=ubicacion_nombre)

            empleados = list(empleados_asignables())
            if not empleados:
                self.stdout.write(self.style.WARNING(
                    "No hay empleados sincronizados desde Nómina: los activos quedan sin asignar."
                ))

            creados = []
            indice_asignacion = 0

            for definicion in DEFINICIONES_TIPOS:
                abbr = definicion["abbr"]
                sub, _ = SubCategoria.objects.get_or_create(
                    nombre=definicion["subcategoria"],
                    categoria=categoria,
                )
                ultimo = maximo_sufijo_codigo_pal(abbr)
                for i in range(por_tipo):
                    codigo = codigo_inventario_pal(abbr, ultimo + i + 1)
                    empleado = (
                        empleados[indice_asignacion % len(empleados)] if empleados else None
                    )
                    asignado_a = empleado.nombre_completo if empleado else "Sin asignar"
                    indice_asignacion += 1

                    creados.append(
                        {
                            "codigo": codigo,
                            "subcategoria": sub.nombre,
                            "marca": definicion["marca"],
                            "modelo": definicion["modelo"],
                            "asignado_a": asignado_a,
                        }
                    )
                    if not dry_run:
                        Activo.objects.create(
                            subcategoria=sub,
                            marca=definicion["marca"],
                            modelo=definicion["modelo"],
                            numero_serial=None,
                            codigo_inventario=codigo,
                            responsable=empleado,
                            ubicacion=ubicacion,
                            observaciones="Cargado con seed_activos_pal",
                            estado=Activo.EstadoActivo.ACTIVO,
                        )

            for fila in creados:
                self.stdout.write(
                    f"  {fila['codigo']}: {fila['subcategoria']} - {fila['marca']} {fila['modelo']} "
                    f"-> {fila['asignado_a']}"
                )
            accion = "Simulados" if dry_run else "Creados"
            self.stdout.write(self.style.SUCCESS(f"{accion}: {len(creados)} activo(s)."))

        if dry_run:
            run()
        else:
            with transaction.atomic():
                run()
