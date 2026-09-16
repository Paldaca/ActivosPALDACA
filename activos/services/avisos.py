"""Avisos de Activos en la campana del Portal (bus de notificaciones).

Solo hechos que cambian responsabilidad: alta y asignación. Editar la
descripción de un equipo no avisa a nadie.
"""

from django.urls import reverse

from .notificaciones_portal import emitir_al_confirmar, url_en_portal

CODIGO_ACTIVO_CREADO = "activos.activo_creado"
CODIGO_ACTIVO_ASIGNADO = "activos.activo_asignado"


def _nombre(usuario):
    """Nombre y Apellido; nunca el username salvo que no haya nombre."""
    return (usuario.get_full_name() or "").strip() or usuario.username


def _descripcion(activo):
    equipo = f"{activo.marca} {activo.modelo}".strip()
    return f"{equipo} · {activo.ubicacion.nombre}" if activo.ubicacion_id else equipo


def _url_ficha_admin(activo):
    """Ficha de gestión: solo la ven administradores de Activos."""
    return url_en_portal(reverse("activos:activo-detail", args=[activo.pk]))


def _url_ficha_propia(activo):
    """Ficha de solo lectura del custodio: lo único que puede abrir sin ser admin."""
    return url_en_portal(reverse("activos:mis-activos-detail", args=[activo.pk]))


def avisar_activo_creado(activo, emisor):
    """Llega a los admins de Activos y, si ya tiene custodio, también a él.

    Con custodio no se emite además `activo_asignado`: el mismo aviso lo cubre.
    """
    payload = {
        "url": _url_ficha_admin(activo),
        "activo_id": activo.pk,
        "codigo_activo": activo.codigo_inventario,
    }
    if activo.usuario_asignado_id:
        payload["usuario_ids"] = [activo.usuario_asignado_id]
    emitir_al_confirmar(
        codigo=CODIGO_ACTIVO_CREADO,
        titulo=f"Nuevo activo {activo.codigo_inventario}",
        cuerpo=f"{_nombre(emisor)} registró {_descripcion(activo)}.",
        payload=payload,
        emisor=emisor,
    )


def avisar_activos_asignados(activos, usuario, emisor):
    """Un solo aviso por persona aunque la asignación masiva mueva varios equipos."""
    if usuario is None or not activos:
        return
    if len(activos) == 1:
        activo = activos[0]
        titulo = f"Se te asignó el activo {activo.codigo_inventario}"
        cuerpo = f"{_nombre(emisor)} te asignó {_descripcion(activo)}."
        url = _url_ficha_propia(activo)
    else:
        titulo = f"Se te asignaron {len(activos)} activos"
        codigos = ", ".join(a.codigo_inventario for a in activos[:5])
        resto = f" y {len(activos) - 5} más" if len(activos) > 5 else ""
        cuerpo = f"{_nombre(emisor)} te asignó {codigos}{resto}."
        url = url_en_portal(reverse("activos:mis-activos-list"))
    emitir_al_confirmar(
        codigo=CODIGO_ACTIVO_ASIGNADO,
        titulo=titulo,
        cuerpo=cuerpo,
        payload={
            "usuario_ids": [usuario.pk],
            "url": url,
            "activo_ids": [a.pk for a in activos],
        },
        emisor=emisor,
    )
