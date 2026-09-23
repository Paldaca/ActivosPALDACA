from functools import wraps
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseForbidden
from django.shortcuts import redirect

from core.embed import embed_signal_response, is_embedded

from .constants import MODULO_CODIGO


def _usuario_tiene_acceso(request):
    user = request.user
    module_codes = getattr(request, "paldaca_module_codes", None)
    if module_codes is not None:
        return user.is_authenticated and MODULO_CODIGO in module_codes
    return (
        user.is_authenticated
        and hasattr(user, "tiene_acceso_modulo")
        and user.tiene_acceso_modulo(MODULO_CODIGO)
    )


def usuario_es_admin_activos(request):
    """Cacheada en el request: el dispatch de la vista, el mixin padre y el
    context processor del footer (`es_admin_activos`) la piden en la misma
    petición; sin cache son 3 consultas iguales en vez de 1."""
    cached = getattr(request, "_activos_es_admin", None)
    if cached is not None:
        return cached
    user = request.user
    resultado = bool(
        user.is_authenticated
        and hasattr(user, "es_administrador_en_modulo")
        and user.es_administrador_en_modulo(MODULO_CODIGO)
    )
    request._activos_es_admin = resultado
    return resultado


# Alias corto para uso interno en este módulo.
_usuario_es_admin = usuario_es_admin_activos


def redirect_to_sso_login(request):
    """Manda al login del Portal conservando la URL actual en ?next=.

    Sin eso, tras autenticarse el usuario cae en el home del Portal y pierde
    el flujo (p. ej. /q/<token>/alta/ desde el móvil).
    """
    login_url = settings.PALDACA_SSO_LOGIN_URL
    next_url = request.build_absolute_uri()
    parts = urlsplit(login_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["next"] = next_url
    return redirect(
        urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
        )
    )


def _deny_unauthenticated(request):
    # Dentro del iframe un redirect al login del Portal anida el shell
    # (LoginPage hace frame-bust → deep link → otra vez iframe) y se percibe
    # como bucle al abrir fichas. El protocolo deja que el shell revalide.
    if is_embedded(request):
        return embed_signal_response(request, "session-expired")
    return redirect_to_sso_login(request)


def requiere_modulo_paldaca(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return _deny_unauthenticated(request)
        if _usuario_tiene_acceso(request):
            return view_func(request, *args, **kwargs)
        return HttpResponseForbidden("No tienes acceso a este programa.")

    return _wrapped


class ModuloActivoRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if _usuario_tiene_acceso(request):
            return super().dispatch(request, *args, **kwargs)
        if not request.user.is_authenticated:
            return _deny_unauthenticated(request)
        if is_embedded(request):
            return embed_signal_response(request, "forbidden")
        return HttpResponseForbidden("No tienes acceso a este programa.")


def _denegar_no_admin(request):
    if is_embedded(request):
        return embed_signal_response(request, "forbidden")
    return HttpResponseForbidden(
        "Necesitas permisos de administrador en Activos para ver esta página."
    )


def requiere_admin_activo(view_func):
    """Como `requiere_modulo_paldaca`, pero además exige rol administrador en Activos.

    Gate de las vistas de gestión (inventario general, catálogos, mantenimientos,
    personas, reportes). Un usuario con acceso al módulo pero sin ese rol solo
    puede ver sus propios activos asignados (`activos:mis-activos-list`).
    """

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return _deny_unauthenticated(request)
        if not _usuario_tiene_acceso(request):
            if is_embedded(request):
                return embed_signal_response(request, "forbidden")
            return HttpResponseForbidden("No tienes acceso a este programa.")
        if not _usuario_es_admin(request):
            return _denegar_no_admin(request)
        return view_func(request, *args, **kwargs)

    return _wrapped


class AdminActivoRequiredMixin(ModuloActivoRequiredMixin):
    """Como `ModuloActivoRequiredMixin`, pero además exige rol administrador en Activos."""

    def dispatch(self, request, *args, **kwargs):
        if (
            request.user.is_authenticated
            and _usuario_tiene_acceso(request)
            and not _usuario_es_admin(request)
        ):
            return _denegar_no_admin(request)
        return super().dispatch(request, *args, **kwargs)
