from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseForbidden
from django.shortcuts import redirect

from core.embed import embed_signal_response, is_embedded

from .constants import MODULO_CODIGO


def _usuario_tiene_acceso(user):
    return (
        user.is_authenticated
        and hasattr(user, "tiene_acceso_modulo")
        and user.tiene_acceso_modulo(MODULO_CODIGO)
    )


def _deny_unauthenticated(request):
    # Dentro del iframe un redirect al login del Portal anida el shell
    # (LoginPage hace frame-bust → deep link → otra vez iframe) y se percibe
    # como bucle al abrir fichas. El protocolo deja que el shell revalide.
    if is_embedded(request):
        return embed_signal_response(request, "session-expired")
    return redirect(settings.PALDACA_SSO_LOGIN_URL)


def requiere_modulo_paldaca(view_func):
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if _usuario_tiene_acceso(request.user):
            return view_func(request, *args, **kwargs)
        return HttpResponseForbidden("No tienes acceso a este programa.")

    return _wrapped


class ModuloActivoRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if _usuario_tiene_acceso(request.user):
            return super().dispatch(request, *args, **kwargs)
        if not request.user.is_authenticated:
            return _deny_unauthenticated(request)
        if is_embedded(request):
            return embed_signal_response(request, "forbidden")
        return HttpResponseForbidden("No tienes acceso a este programa.")
