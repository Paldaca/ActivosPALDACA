"""Avisos de Activos en la campana del Portal (bus de notificaciones).

Dos mecanismos, a propósito (mismo patrón híbrido que HDT):

- **Al momento del hecho** (alta, asignación): se emite donde ocurre el
  cambio, vía `emitir_al_confirmar` (después del commit).
- **Por reloj** (usuario desactivado con equipos): no hay ningún punto de
  código en este repo que lo detecte — la desactivación ocurre fuera de
  Activos (panel de superadmin del Portal) — así que lo evalúa el
  despachador `enviar_notificaciones_activos`, vía `emitir_evento` directo.
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from ..models import Activo, AvisoPorUmbral, AvisoUsuarioInactivo, EtiquetaQR, HistorialMovimiento
from . import notificaciones_portal
from .notificaciones_portal import emitir_al_confirmar, url_en_portal

CODIGO_ACTIVO_CREADO = "activos.activo_creado"
CODIGO_ACTIVO_ASIGNADO = "activos.activo_asignado"
CODIGO_ACTIVO_DESASIGNADO = "activos.activo_desasignado"
CODIGO_MANTENIMIENTO_INICIADO = "activos.mantenimiento_iniciado"
CODIGO_MANTENIMIENTO_FINALIZADO = "activos.mantenimiento_finalizado"
CODIGO_ACTIVO_BAJA = "activos.activo_baja"
CODIGO_USUARIO_INACTIVO = "activos.usuario_inactivo_con_equipos"
CODIGO_ETIQUETA_SIN_VINCULAR = "activos.etiqueta_sin_vincular"
CODIGO_ASIGNACION_SIN_PLANILLA = "activos.asignacion_sin_planilla"


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


# --- etiqueta_sin_vincular (regla por reloj) --------------------------------


def etiquetas_sin_vincular(dias=None):
    """EtiquetaQR en PENDIENTE hace más de N días, sin aviso vigente."""
    dias = settings.ACTIVOS_UMBRAL_ETIQUETA_SIN_VINCULAR_DIAS if dias is None else dias
    limite = timezone.now() - timedelta(days=dias)
    ya_avisadas = AvisoPorUmbral.objects.filter(
        regla=AvisoPorUmbral.REGLA_ETIQUETA_SIN_VINCULAR
    ).values_list("objeto_id", flat=True)
    return list(
        EtiquetaQR.objects.filter(
            estado=EtiquetaQR.EstadoEtiqueta.PENDIENTE,
            fecha_creacion__lte=limite,
        )
        .exclude(pk__in=ya_avisadas)
        .select_related("creada_por")
        .order_by("fecha_creacion")
    )


def _limpiar_avisos_etiqueta_sin_vincular():
    """Libera el marcador de etiquetas que ya se vincularon o se anularon."""
    for aviso in AvisoPorUmbral.objects.filter(
        regla=AvisoPorUmbral.REGLA_ETIQUETA_SIN_VINCULAR
    ):
        if not EtiquetaQR.objects.filter(
            pk=aviso.objeto_id, estado=EtiquetaQR.EstadoEtiqueta.PENDIENTE
        ).exists():
            aviso.delete()


def _avisar_etiquetas_de(etiquetas, creador):
    """Un aviso por creador (o `None` para las sin creador registrado)."""
    dias = settings.ACTIVOS_UMBRAL_ETIQUETA_SIN_VINCULAR_DIAS
    if len(etiquetas) == 1:
        etiqueta = etiquetas[0]
        titulo = f"Etiqueta {etiqueta.codigo_reservado} sigue sin vincular"
        cuerpo = (
            f"Se imprimió hace más de {dias} días y ningún activo la usa todavía."
        )
    else:
        titulo = f"{len(etiquetas)} etiquetas siguen sin vincular"
        codigos = ", ".join(e.codigo_reservado for e in etiquetas[:5])
        resto = f" y {len(etiquetas) - 5} más" if len(etiquetas) > 5 else ""
        cuerpo = f"Llevan más de {dias} días impresas sin vincular: {codigos}{resto}."

    payload = {
        "url": url_en_portal(reverse("activos:etiqueta-list")),
        "etiqueta_ids": [e.pk for e in etiquetas],
    }
    if creador is not None:
        payload["usuario_ids"] = [creador.pk]

    enviado = notificaciones_portal.emitir_evento(
        codigo=CODIGO_ETIQUETA_SIN_VINCULAR,
        titulo=titulo,
        cuerpo=cuerpo,
        payload=payload,
    )
    if not enviado:
        return False
    AvisoPorUmbral.objects.bulk_create(
        [
            AvisoPorUmbral(
                regla=AvisoPorUmbral.REGLA_ETIQUETA_SIN_VINCULAR, objeto_id=e.pk
            )
            for e in etiquetas
        ]
    )
    return True


def avisar_etiquetas_sin_vincular():
    """Un aviso por creador (agrupa sus etiquetas); siempre llega también a admins.

    Devuelve cuántas etiquetas quedaron incluidas en algún aviso (0 si no
    había candidatas nuevas o el Portal no aceptó nada).
    """
    _limpiar_avisos_etiqueta_sin_vincular()
    candidatas = etiquetas_sin_vincular()
    if not candidatas:
        return 0

    por_creador = {}
    sin_creador = []
    for etiqueta in candidatas:
        if etiqueta.creada_por_id:
            grupo = por_creador.setdefault(etiqueta.creada_por_id, (etiqueta.creada_por, []))
            grupo[1].append(etiqueta)
        else:
            sin_creador.append(etiqueta)

    incluidas = 0
    for creador, etiquetas in por_creador.values():
        if _avisar_etiquetas_de(etiquetas, creador):
            incluidas += len(etiquetas)
    if sin_creador and _avisar_etiquetas_de(sin_creador, None):
        incluidas += len(sin_creador)
    return incluidas


# --- asignacion_sin_planilla (regla por reloj) ------------------------------


def asignaciones_sin_planilla(dias=None):
    """Reasignaciones sin planilla archivada hace más de N días, sin aviso vigente."""
    dias = settings.ACTIVOS_UMBRAL_ASIGNACION_SIN_PLANILLA_DIAS if dias is None else dias
    limite = timezone.now() - timedelta(days=dias)
    ya_avisados = AvisoPorUmbral.objects.filter(
        regla=AvisoPorUmbral.REGLA_ASIGNACION_SIN_PLANILLA
    ).values_list("objeto_id", flat=True)
    return list(
        HistorialMovimiento.objects.filter(
            tipo_movimiento=HistorialMovimiento.TipoMovimiento.REASIGNACION,
            fecha_movimiento__lte=limite,
        )
        .filter(Q(archivo_planilla="") | Q(archivo_planilla__isnull=True))
        .exclude(pk__in=ya_avisados)
        .select_related("activo")
        .order_by("fecha_movimiento")
    )


def _limpiar_avisos_asignacion_sin_planilla():
    """Libera el marcador de reasignaciones a las que ya se les archivó la planilla."""
    for aviso in AvisoPorUmbral.objects.filter(
        regla=AvisoPorUmbral.REGLA_ASIGNACION_SIN_PLANILLA
    ):
        movimiento = HistorialMovimiento.objects.filter(pk=aviso.objeto_id).first()
        if movimiento is None or movimiento.archivo_planilla:
            aviso.delete()


def avisar_asignaciones_sin_planilla():
    """Un solo aviso a los admins por corrida, listando las reasignaciones sin planilla.

    Devuelve cuántas se incluyeron (0 si no había candidatas nuevas o el
    Portal no aceptó el aviso).
    """
    _limpiar_avisos_asignacion_sin_planilla()
    candidatos = asignaciones_sin_planilla()
    if not candidatos:
        return 0

    dias = settings.ACTIVOS_UMBRAL_ASIGNACION_SIN_PLANILLA_DIAS
    if len(candidatos) == 1:
        movimiento = candidatos[0]
        titulo = f"{movimiento.activo.codigo_inventario} sigue sin planilla de entrega"
        cuerpo = (
            f"Se reasignó hace más de {dias} días y no tiene planilla firmada archivada."
        )
        url = _url_ficha_admin(movimiento.activo)
    else:
        titulo = f"{len(candidatos)} reasignaciones siguen sin planilla de entrega"
        codigos = ", ".join(m.activo.codigo_inventario for m in candidatos[:5])
        resto = f" y {len(candidatos) - 5} más" if len(candidatos) > 5 else ""
        cuerpo = (
            f"Llevan más de {dias} días sin planilla archivada: {codigos}{resto}."
        )
        url = url_en_portal(reverse("activos:activo-list"))

    enviado = notificaciones_portal.emitir_evento(
        codigo=CODIGO_ASIGNACION_SIN_PLANILLA,
        titulo=titulo,
        cuerpo=cuerpo,
        payload={"url": url, "movimiento_ids": [m.pk for m in candidatos]},
    )
    if not enviado:
        return 0
    AvisoPorUmbral.objects.bulk_create(
        [
            AvisoPorUmbral(
                regla=AvisoPorUmbral.REGLA_ASIGNACION_SIN_PLANILLA, objeto_id=m.pk
            )
            for m in candidatos
        ]
    )
    return len(candidatos)
