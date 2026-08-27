"""Vistas ANÓNIMAS del módulo de Activos.

Fichero aparte de `views.py` a propósito: todo lo que hay allí pasa por
`ModuloActivoRequiredMixin` o `@requiere_modulo_paldaca`, y esa uniformidad es
una garantía que conviene poder leer de un vistazo. Lo que se sirve sin sesión
vive aquí, aislado, para que añadir una vista pública sea siempre una decisión
consciente y no un descuido al editar el fichero grande.

Contrato de privacidad de la ficha pública (`/q/<token>/`): la etiqueta es un
secreto portador impreso en un adhesivo, así que quien tenga el equipo delante
puede leer lo que muestre esta página. Se publica lo que identifica al equipo
más el nombre y apellido de quien lo tiene asignado. NO se publican
observaciones, historial, mantenimientos ni ningún otro dato de la persona.
"""

from django.core.cache import cache
from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .constants import MODULO_CODIGO
from .models import EtiquetaQR

#: Tokens fallidos tolerados por IP y ventana antes de cortar. El token tiene
#: 72 bits, así que esto no es lo que impide adivinarlo: evita que un escáner
#: automático use la ruta como oráculo barato.
LIMITE_FALLOS = 30
VENTANA_FALLOS_SEG = 300


def _ip(request):
    reenviada = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if reenviada:
        return reenviada.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or "desconocida"


def _registrar_fallo(request):
    clave = f"qr:fallos:{_ip(request)}"
    try:
        intentos = cache.get_or_set(clave, 0, VENTANA_FALLOS_SEG)
        cache.set(clave, intentos + 1, VENTANA_FALLOS_SEG)
    except Exception:
        # Un backend de caché caído no puede tumbar la ficha pública: el
        # límite es una defensa en profundidad, no el control de acceso.
        pass


def _demasiados_fallos(request) -> bool:
    try:
        return (cache.get(f"qr:fallos:{_ip(request)}") or 0) >= LIMITE_FALLOS
    except Exception:
        return False


def _puede_gestionar(user) -> bool:
    return (
        user.is_authenticated
        and hasattr(user, "tiene_acceso_modulo")
        and user.tiene_acceso_modulo(MODULO_CODIGO)
    )


@require_GET
def etiqueta_publica(request, token):
    """Resuelve una etiqueta escaneada. Tres desenlaces posibles.

    - Pendiente  -> invita a cargar los datos del activo (el alta exige sesión).
    - Vinculada  -> ficha pública del activo.
    - Anulada, o vinculada a un activo ya borrado -> mensaje neutro.
    """
    if _demasiados_fallos(request):
        raise Http404

    etiqueta = (
        EtiquetaQR.objects.select_related(
            "subcategoria__categoria",
            "activo__subcategoria__categoria",
            "activo__ubicacion",
            "activo__usuario_asignado",
        )
        .filter(token=token)
        .first()
    )

    if etiqueta is None:
        _registrar_fallo(request)
        raise Http404

    puede_gestionar = _puede_gestionar(request.user)

    if etiqueta.estado == EtiquetaQR.EstadoEtiqueta.ANULADA:
        situacion = "anulada"
    elif etiqueta.activo_id is None:
        # Cubre dos casos con el mismo mensaje: etiqueta impresa que nadie ha
        # completado todavía, y etiqueta cuyo activo se eliminó (SET_NULL).
        situacion = "pendiente" if etiqueta.esta_pendiente else "sin_activo"
    else:
        situacion = "vinculada"

    respuesta = render(
        request,
        "activos/publico/etiqueta.html",
        {
            "etiqueta": etiqueta,
            "activo": etiqueta.activo,
            "situacion": situacion,
            "puede_gestionar": puede_gestionar,
        },
    )
    # La ficha de un activo concreto no tiene por qué acabar en un buscador.
    respuesta["X-Robots-Tag"] = "noindex, nofollow"
    return respuesta
