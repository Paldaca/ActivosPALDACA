"""Etiquetas QR vinculadas a activos ya registrados (alta manual)."""

from __future__ import annotations

from django.utils import timezone

from activos.models import Activo, EtiquetaQR


def crear_etiqueta_vinculada_para_activo(
    activo: Activo,
    *,
    creada_por=None,
) -> tuple[EtiquetaQR, bool]:
    """Crea (o reutiliza) la etiqueta vigente de un activo existente.

    Devuelve ``(etiqueta, creada)``. Si ya hay una vinculada, la devuelve sin
    duplicar — útil para reimprimir tras un alta manual.
    """
    existente = (
        EtiquetaQR.objects.filter(
            activo=activo,
            estado=EtiquetaQR.EstadoEtiqueta.VINCULADA,
        )
        .order_by("-fecha_vinculacion")
        .first()
    )
    if existente:
        return existente, False

    ahora = timezone.now()
    etiqueta = EtiquetaQR(
        codigo_reservado=activo.codigo_inventario,
        subcategoria=activo.subcategoria,
        activo=activo,
        estado=EtiquetaQR.EstadoEtiqueta.VINCULADA,
        fecha_vinculacion=ahora,
        creada_por=creada_por,
        token=EtiquetaQR.generar_token(),
    )
    etiqueta.save()
    return etiqueta, True
