"""Avisos de Activos en la campana del Portal (bus de notificaciones).

Dos mecanismos, a propósito (mismo patrón híbrido que HDT):

- **Al momento del hecho** (alta, asignación): se emite donde ocurre el
  cambio, vía `emitir_al_confirmar` (después del commit).
- **Por reloj** (usuario desactivado con equipos): no hay ningún punto de
  código en este repo que lo detecte — la desactivación ocurre fuera de
  Activos (panel de superadmin del Portal) — así que lo evalúa el
  despachador `enviar_notificaciones_activos`, vía `emitir_evento` directo.
"""

from django.contrib.auth import get_user_model
from django.urls import reverse

from ..models import Activo, AvisoUsuarioInactivo
from . import notificaciones_portal
from .notificaciones_portal import emitir_al_confirmar, url_en_portal

CODIGO_ACTIVO_CREADO = "activos.activo_creado"
CODIGO_ACTIVO_ASIGNADO = "activos.activo_asignado"
CODIGO_ACTIVO_DESASIGNADO = "activos.activo_desasignado"
CODIGO_MANTENIMIENTO_INICIADO = "activos.mantenimiento_iniciado"
CODIGO_MANTENIMIENTO_FINALIZADO = "activos.mantenimiento_finalizado"
CODIGO_ACTIVO_BAJA = "activos.activo_baja"
CODIGO_USUARIO_INACTIVO = "activos.usuario_inactivo_con_equipos"


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


def avisar_activos_desasignados(activos, usuario, emisor):
    """Al custodio ANTERIOR que pierde uno o varios equipos (incluye "dejar sin asignar").

    Espejo de `avisar_activos_asignados`, pero el deep link nunca puede ir a la
    ficha del activo: esa persona ya no lo tiene, así que `mis-activos-detail`
    le daría 404. Va siempre a su propio listado.
    """
    if usuario is None or not activos:
        return
    if len(activos) == 1:
        activo = activos[0]
        titulo = f"Ya no tienes a tu cargo el activo {activo.codigo_inventario}"
        cuerpo = f"{_nombre(emisor)} te quitó {_descripcion(activo)}."
    else:
        titulo = f"Ya no tienes a tu cargo {len(activos)} activos"
        codigos = ", ".join(a.codigo_inventario for a in activos[:5])
        resto = f" y {len(activos) - 5} más" if len(activos) > 5 else ""
        cuerpo = f"{_nombre(emisor)} te quitó {codigos}{resto}."
    emitir_al_confirmar(
        codigo=CODIGO_ACTIVO_DESASIGNADO,
        titulo=titulo,
        cuerpo=cuerpo,
        payload={
            "usuario_ids": [usuario.pk],
            "url": url_en_portal(reverse("activos:mis-activos-list")),
            "activo_ids": [a.pk for a in activos],
        },
        emisor=emisor,
    )


def avisar_mantenimiento_iniciado(mantenimiento, emisor):
    """El activo entra a mantenimiento. Sin custodio, no hay a quién avisar."""
    activo = mantenimiento.activo
    usuario = activo.usuario_asignado
    if usuario is None:
        return
    emitir_al_confirmar(
        codigo=CODIGO_MANTENIMIENTO_INICIADO,
        titulo=f"{activo.codigo_inventario} entró a mantenimiento",
        cuerpo=(
            f"{_nombre(emisor)} registró un mantenimiento para {_descripcion(activo)}. "
            "Puede no estar disponible por un tiempo."
        ),
        payload={
            "usuario_ids": [usuario.pk],
            "url": _url_ficha_propia(activo),
            "activo_id": activo.pk,
            "mantenimiento_id": mantenimiento.pk,
        },
        emisor=emisor,
    )


def avisar_mantenimiento_finalizado(mantenimiento, emisor):
    """Se cerró el último mantenimiento en proceso y el activo vuelve a servicio."""
    activo = mantenimiento.activo
    usuario = activo.usuario_asignado
    if usuario is None:
        return
    emitir_al_confirmar(
        codigo=CODIGO_MANTENIMIENTO_FINALIZADO,
        titulo=f"{activo.codigo_inventario} volvió de mantenimiento",
        cuerpo=f"{_descripcion(activo)} ya está disponible de nuevo.",
        payload={
            "usuario_ids": [usuario.pk],
            "url": _url_ficha_propia(activo),
            "activo_id": activo.pk,
            "mantenimiento_id": mantenimiento.pk,
        },
        emisor=emisor,
    )


def avisar_activo_baja(activo, emisor, *, eliminado=False):
    """El activo pasa a `IN` o se elimina. Llega al custodio (si tenía) y a admins.

    `eliminado=True` cuando la ficha ya no va a existir (DELETE): el deep link
    no puede apuntar a `activo-detail`/`mis-activos-detail` (404 seguro), así
    que va al listado. Los textos se arman aquí mismo, antes de que
    `ActivoDeleteView` borre la fila (BR-ACT-12): `emitir_al_confirmar` solo
    difiere la llamada HTTP, no la lectura de `activo`.
    """
    if eliminado:
        titulo = f"Se eliminó el activo {activo.codigo_inventario}"
        cuerpo = f"{_nombre(emisor)} eliminó {_descripcion(activo)}."
        url = url_en_portal(reverse("activos:activo-list"))
    else:
        titulo = f"{activo.codigo_inventario} fue dado de baja"
        cuerpo = f"{_nombre(emisor)} dio de baja a {_descripcion(activo)}."
        url = _url_ficha_admin(activo)
    payload = {
        "url": url,
        "activo_id": activo.pk,
        "codigo_activo": activo.codigo_inventario,
    }
    if activo.usuario_asignado_id:
        payload["usuario_ids"] = [activo.usuario_asignado_id]
    emitir_al_confirmar(
        codigo=CODIGO_ACTIVO_BAJA,
        titulo=titulo,
        cuerpo=cuerpo,
        payload=payload,
        emisor=emisor,
    )


# --- Regla por reloj (la evalúa el despachador) -----------------------------


def usuarios_inactivos_con_equipos():
    """Usuarios `is_active=False` que siguen con activos asignados.

    Excluye a quienes ya tienen un aviso vigente (`AvisoUsuarioInactivo`): no
    se repite mientras la situación no cambie.
    """
    ya_avisados = AvisoUsuarioInactivo.objects.values_list("usuario_id", flat=True)
    return list(
        get_user_model()
        .objects.filter(is_active=False, activos_asignados__isnull=False)
        .exclude(pk__in=ya_avisados)
        .distinct()
        .order_by("username")
    )


def _limpiar_avisos_resueltos():
    """Libera el marcador de quien se reactivó o ya no tiene equipo asignado.

    Así, si la situación se repite más adelante, vuelve a avisar en vez de
    quedar silenciada para siempre.
    """
    for aviso in AvisoUsuarioInactivo.objects.select_related("usuario"):
        usuario = aviso.usuario
        if usuario.is_active or not Activo.objects.filter(usuario_asignado=usuario).exists():
            aviso.delete()


def avisar_usuarios_inactivos_con_equipos():
    """Un solo aviso a los admins por corrida, listando a quien se detectó.

    Cada usuario incluido queda marcado (`AvisoUsuarioInactivo`) para no
    repetirse en la corrida del día siguiente mientras nadie reasigne su
    equipo. Devuelve cuántos usuarios se incluyeron en el aviso (0 si no
    había candidatos nuevos o el Portal no lo aceptó).
    """
    _limpiar_avisos_resueltos()
    candidatos = usuarios_inactivos_con_equipos()
    if not candidatos:
        return 0

    conteos = {
        usuario.pk: Activo.objects.filter(usuario_asignado=usuario).count()
        for usuario in candidatos
    }

    if len(candidatos) == 1:
        usuario = candidatos[0]
        n = conteos[usuario.pk]
        titulo = f"{_nombre(usuario)} fue desactivado con {n} equipo{'s' if n != 1 else ''} asignado{'s' if n != 1 else ''}"
        cuerpo = (
            f"Su cuenta se desactivó y sigue como custodio de {n} "
            f"equipo{'s' if n != 1 else ''}. Reasígna{'los' if n != 1 else 'lo'} desde su ficha."
        )
        url = url_en_portal(reverse("usuarios:usuario-profile", args=[usuario.pk]))
    else:
        detalle = "; ".join(f"{_nombre(u)} ({conteos[u.pk]})" for u in candidatos)
        titulo = f"{len(candidatos)} usuarios desactivados siguen con equipos asignados"
        cuerpo = f"Reasigna sus equipos antes de que queden huérfanos: {detalle}."
        url = url_en_portal(reverse("usuarios:usuario-search"))

    enviado = notificaciones_portal.emitir_evento(
        codigo=CODIGO_USUARIO_INACTIVO,
        titulo=titulo,
        cuerpo=cuerpo,
        payload={"url": url, "usuario_ids": [u.pk for u in candidatos]},
    )
    if not enviado:
        return 0
    AvisoUsuarioInactivo.objects.bulk_create(
        [AvisoUsuarioInactivo(usuario=u) for u in candidatos]
    )
    return len(candidatos)
