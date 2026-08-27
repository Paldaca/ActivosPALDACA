"""Reserva de códigos de inventario `PAL-{PREFIJO}-NNN`.

Punto ÚNICO donde se decide el siguiente número de una subcategoría. Existe
porque el código dejó de tener una sola fuente de verdad: un código puede estar
ocupado por un activo ya registrado (`activos_activo.codigo_inventario`) o
apartado por una etiqueta QR impresa que todavía nadie ha completado
(`activos_etiqueta_qr.codigo_reservado`).

El cálculo anterior vivía en `Activo._generar_codigo_inventario()` y leía una
sola tabla sin bloqueo: dos altas simultáneas podían quedarse con el mismo
número. Imprimir una hoja de 30 etiquetas convierte esa carrera en el caso
normal, no en el excepcional, así que la reserva se hace bajo bloqueo de fila.
"""

import re

from django.db import IntegrityError, connection, transaction

#: Cuántas veces se reintenta si otra transacción se adelanta pese al bloqueo.
#: Solo puede ocurrir en backends sin `SELECT ... FOR UPDATE` (SQLite en tests).
MAX_REINTENTOS = 5

#: `PAL-LAP-007` -> 7. Ancla al final para no confundirse con prefijos numéricos.
_SUFIJO_NUMERICO = re.compile(r"-(\d+)$")


def _base(subcategoria) -> str:
    prefijo = (subcategoria.prefijo or "").strip().upper()
    return f"PAL-{prefijo}-"


def _ultimo_numero(base: str) -> int:
    """Mayor número ya usado o apartado bajo `base`, o 0 si no hay ninguno.

    Se recorre en Python en lugar de con MAX() en SQL porque el número es un
    sufijo de texto: `PAL-X-1000` ordena antes que `PAL-X-999` alfabéticamente,
    y basta con que el inventario pase de 999 unidades de una subcategoría para
    que un MAX() textual empiece a repetir códigos.
    """
    from activos.models import Activo, EtiquetaQR

    codigos = list(
        Activo.objects.filter(codigo_inventario__startswith=base).values_list(
            "codigo_inventario", flat=True
        )
    )
    codigos += list(
        EtiquetaQR.objects.filter(codigo_reservado__startswith=base).values_list(
            "codigo_reservado", flat=True
        )
    )

    ultimo = 0
    for codigo in codigos:
        match = _SUFIJO_NUMERICO.search(codigo or "")
        if not match:
            continue
        numero = int(match.group(1))
        if numero > ultimo:
            ultimo = numero
    return ultimo


def reservar_codigos(subcategoria, cantidad=1):
    """Devuelve `cantidad` códigos consecutivos libres para `subcategoria`.

    NO persiste nada: devolver los códigos y guardarlos (en un `Activo` o en
    varias `EtiquetaQR`) es responsabilidad de quien llama, que debe hacerlo
    dentro de la MISMA transacción para que el bloqueo siga vigente.

    El bloqueo se toma sobre la fila de la subcategoría: es el recurso que
    realmente se está serializando (su contador), y bloquear ahí no interfiere
    con altas de otras subcategorías.
    """
    if cantidad < 1:
        raise ValueError("La cantidad de códigos a reservar debe ser al menos 1.")

    from activos.models import SubCategoria

    for intento in range(MAX_REINTENTOS):
        try:
            with transaction.atomic():
                bloqueadas = SubCategoria.objects.filter(pk=subcategoria.pk)
                # SQLite (tests) no implementa SELECT ... FOR UPDATE y Django
                # lanzaría NotSupportedError. Ahí la atomicidad la da el lock de
                # escritura del propio fichero, y el reintento cubre el resto.
                if connection.features.has_select_for_update:
                    bloqueadas = bloqueadas.select_for_update()

                fijada = bloqueadas.first()
                if fijada is None:
                    raise SubCategoria.DoesNotExist(
                        f"La subcategoría {subcategoria.pk} ya no existe."
                    )

                base = _base(fijada)
                desde = _ultimo_numero(base) + 1
                return [f"{base}{n:03d}" for n in range(desde, desde + cantidad)]
        except IntegrityError:
            if intento == MAX_REINTENTOS - 1:
                raise

    raise IntegrityError(
        "No se pudo reservar un código de inventario libre tras "
        f"{MAX_REINTENTOS} intentos."
    )


def siguiente_codigo(subcategoria) -> str:
    """Azúcar para el alta de un solo activo."""
    return reservar_codigos(subcategoria, cantidad=1)[0]
