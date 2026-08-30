from django.conf import settings
from django.http import HttpResponseServerError, JsonResponse
from django.shortcuts import redirect

from .embed import embed_signal_response, is_embedded
from .models import Modulo
from .session_logout import apply_paldaca_cookie_clearance, close_paldaca_session
from django.template.loader import render_to_string
from django.utils.deprecation import MiddlewareMixin
import logging

logger = logging.getLogger(__name__)


class PaldacaSessionMiddleware:
    SESSION_REVISION_KEY = "paldaca_auth_revision"
    SESSION_ROL_KEY = "paldaca_rol"
    SESSION_DISCIPLINA_KEY = "paldaca_disciplina_id"
    SESSION_PERFIL_KEY = "paldaca_perfil_id"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return self.get_response(request)

        if not hasattr(request, "session"):
            return self.get_response(request)

        current_user = user
        if not current_user.is_active:
            return self._close_session(request)

        module_codes = self._active_module_codes(current_user)
        request.paldaca_module_codes = frozenset(module_codes)
        current_revision = current_user.get_auth_revision(module_codes)
        session_revision = request.session.get(self.SESSION_REVISION_KEY)

        if not session_revision:
            self._store_snapshot(request, current_user, current_revision)
            return self.get_response(request)

        if session_revision != current_revision:
            strict_mode = (
                str(
                    getattr(settings, "PALDACA_STRICT_SESSION_CONSISTENCY", "true")
                ).lower()
                == "true"
            )
            if strict_mode:
                return self._close_session(request)
            self._store_snapshot(request, current_user, current_revision)

        return self.get_response(request)

    @staticmethod
    def _active_module_codes(user):
        if user.is_superuser:
            return list(
                Modulo.objects.filter(activo=True).values_list(
                    "codigo", flat=True
                )
            )
        return user._codigos_modulos_asignados()

    def _store_snapshot(self, request, user, revision):
        request.session[self.SESSION_REVISION_KEY] = revision
        request.session[self.SESSION_ROL_KEY] = user.rol
        request.session[self.SESSION_DISCIPLINA_KEY] = user.disciplina_id
        request.session[self.SESSION_PERFIL_KEY] = user.perfil_id

    def _close_session(self, request):
        close_paldaca_session(request)

        login_url = getattr(settings, "PALDACA_SSO_LOGIN_URL", "/login/")
        accept_header = request.headers.get("Accept", "").lower()
        is_api_request = request.path.startswith("/api/") or "application/json" in accept_header

        if is_api_request:
            response = JsonResponse(
                {"detail": "La sesion se cerro porque cambiaron tus permisos."},
                status=401,
            )
            return apply_paldaca_cookie_clearance(response)

        # Dentro del shell, un redirect al login navegaria el propio iframe y el
        # usuario veria el formulario de login incrustado en el area de trabajo,
        # con el sidebar del Portal alrededor y sin forma de completar el flujo.
        # Se avisa al shell y que sea el quien saque al usuario.
        if is_embedded(request):
            response = embed_signal_response(request, "session-expired")
            return apply_paldaca_cookie_clearance(response)

        response = redirect(login_url)
        return apply_paldaca_cookie_clearance(response)


class ErrorHandlingMiddleware(MiddlewareMixin):
    """
    Middleware personalizado para capturar y manejar errores de manera elegante
    """
    
    def process_exception(self, request, exception):
        """
        Captura todas las excepciones no manejadas y las registra
        """
        from django.core.exceptions import PermissionDenied
        from django.http import Http404

        # Dejar que Django resuelva 404/403 con sus handlers normales.
        if isinstance(exception, (Http404, PermissionDenied)):
            return None

        # Obtener información del usuario
        user_info = "Anónimo"
        if hasattr(request, 'user') and request.user.is_authenticated:
            user_info = f"{request.user.username} (ID: {request.user.id})"
        
        # Registrar el error completo
        logger.error(
            f"Error no manejado en {request.path} - "
            f"Usuario: {user_info} - "
            f"IP: {self.get_client_ip(request)} - "
            f"Error: {str(exception)}",
            exc_info=True,
            extra={
                'user': user_info,
                'path': request.path,
                'method': request.method,
                'ip': self.get_client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
            }
        )
        
        # En modo DEBUG, dejar que Django maneje el error normalmente
        if settings.DEBUG:
            return None
        
        # En producción, mostrar una página de error personalizada
        try:
            error_html = render_to_string('core/error_500.html', {
                'error_id': id(exception),  # ID único para el error
                'path': request.path,
            })
            return HttpResponseServerError(error_html)
        except Exception as render_error:
            # Si incluso el renderizado falla, devolver un error básico
            logger.critical(f"Error crítico al renderizar página de error: {render_error}")
            return HttpResponseServerError(
                "<h1>Error del Servidor</h1>"
                "<p>Ha ocurrido un error interno. Por favor, contacte al administrador.</p>"
            )
    
    def get_client_ip(self, request):
        """
        Obtiene la IP real del cliente
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Middleware para agregar headers de seguridad
    """
    
    def process_response(self, request, response):
        # X-Frame-Options ya no se fija aqui. Este modulo se embebe en el shell
        # del Portal (cpaldaca.com/activos), y 'DENY' lo impedia; ademas la
        # cabecera no admite lista de origenes. El control de framing lo hace
        # core.embed.PaldacaEmbedMiddleware con CSP frame-ancestors, que
        # restringe el enmarcado al Portal y es mas estricto que no tener nada.

        # Prevenir MIME type sniffing
        response['X-Content-Type-Options'] = 'nosniff'
        
        # Habilitar XSS protection
        response['X-XSS-Protection'] = '1; mode=block'
        
        # Referrer policy
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        return response
