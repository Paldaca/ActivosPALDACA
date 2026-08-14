"""
Soporte para renderizar este satélite DENTRO del shell del Portal
(`cpaldaca.com/<modulo>`), en lugar de como sitio suelto en su subdominio.

Archivo deliberadamente independiente de `core/middleware.py`: ese fichero ya
diverge entre los repos de la Suite (aquí conviven tres clases que no existen en
los demás), así que un módulo aparte se puede copiar tal cual a Calidad, Códigos
y HojadeTiempo sin resolver conflictos. Todo lo específico del repo se lee de
`settings`, no se codifica aquí.

Contrato de mensajería con el shell: `paldaca-embed` v1. La contraparte vive en
`Portal-Paldaca/frontend/src/components/module-frame/protocol.ts`.
"""

from urllib.parse import urlsplit

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils.html import escape

#: Atributo que el middleware deja en el request.
EMBED_REQUEST_ATTR = "paldaca_embedded"

#: Cookie host-only de respaldo, para navegadores sin cabeceras `Sec-Fetch-*`.
EMBED_COOKIE = "paldaca_embed"
EMBED_QUERY_PARAM = "paldaca_embed"

#: Válvula de escape: permite servir el satélite suelto para depurar.
STANDALONE_COOKIE = "paldaca_standalone"
STANDALONE_QUERY_PARAM = "paldaca_standalone"

DEFAULT_EXCLUDED_PREFIXES = ("/admin/", "/static/", "/media/", "/logout/", "/healthz/")


def is_embedded(request) -> bool:
    """¿Esta petición se está sirviendo dentro del iframe del Portal?"""
    return bool(getattr(request, EMBED_REQUEST_ATTR, False))


def _modulo_codigo() -> str:
    return getattr(settings, "PALDACA_MODULO_CODIGO", "")


def _portal_origin() -> str:
    """Origen exacto del shell, para `postMessage(..., targetOrigin)`."""
    raw = (getattr(settings, "PALDACA_PORTAL_URL", "") or "").strip()
    parts = urlsplit(raw)
    if parts.scheme and parts.netloc:
        return f"{parts.scheme}://{parts.netloc}"
    return raw.rstrip("/")


def embed_signal_response(request, message_type: str, status: int = 200):
    """
    Documento mínimo cuyo único fin es avisar al shell por `postMessage`.

    Se usa cuando el satélite tendría que hacer un redirect de página completa
    (sesión caducada, sin acceso): dentro del iframe ese redirect navegaría el
    propio iframe y el usuario vería el login del Portal incrustado en el área
    de trabajo, sin manera de completar el flujo.

    El estado es 200 a propósito: el navegador debe renderizar el HTML para que
    el script llegue a ejecutarse. La semántica del error viaja en el mensaje.
    """
    origin = escape(_portal_origin())
    app = escape(_modulo_codigo())
    kind = escape(message_type)
    html = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><title>Paldaca</title></head>
<body>
<script>
  try {{
    window.parent.postMessage(
      {{ v: 1, source: "paldaca-embed", type: "{kind}", app: "{app}" }},
      "{origin}"
    );
  }} catch (e) {{ /* sin padre alcanzable: no hay nada que avisar */ }}
</script>
</body></html>"""
    return HttpResponse(html, status=status)


class PaldacaEmbedMiddleware:
    """
    Hace embebible este satélite y mantiene coherente la experiencia de shell.

    POSICIÓN EN `MIDDLEWARE` (importa, y por dos motivos distintos):

    - Debe ir DESPUÉS de `AuthenticationMiddleware` y ANTES de
      `PaldacaSessionMiddleware`. Lo primero, porque el redirect al shell
      necesita `request.user`. Lo segundo, porque `PaldacaSessionMiddleware`
      puede cortocircuitar la petición al cerrar la sesión, y necesita que
      `request.paldaca_embedded` ya esté puesto para responder con el protocolo
      en vez de con un redirect.

    - Su fase de respuesta corre DESPUÉS de la de todos los middlewares que
      vengan detrás (el orden de respuesta es inverso), así que tiene la última
      palabra sobre las cabeceras de framing aunque otro middleware posterior
      vuelva a escribir `X-Frame-Options`.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        standalone = self._resolve_standalone(request)
        embedded = self._resolve_embedded(request, standalone)
        setattr(request, EMBED_REQUEST_ATTR, embedded)

        redirect_response = self._maybe_redirect_to_shell(
            request, embedded=embedded, standalone=standalone
        )
        if redirect_response is not None:
            return self._apply_cookies(request, redirect_response, embedded, standalone)

        response = self.get_response(request)
        self._apply_frame_headers(response)
        return self._apply_cookies(request, response, embedded, standalone)

    # -- detección ---------------------------------------------------------

    def _resolve_standalone(self, request) -> bool:
        raw = request.GET.get(STANDALONE_QUERY_PARAM)
        if raw is not None:
            return raw not in ("0", "false", "no", "")
        return request.COOKIES.get(STANDALONE_COOKIE) == "1"

    def _resolve_embedded(self, request, standalone: bool) -> bool:
        if standalone:
            return False

        # Capa 1: `Sec-Fetch-Dest` viaja en CADA navegación de documento, así
        # que sobrevive a los clics y a los POST+redirect del satélite sin
        # necesidad de estado en servidor. Es la señal buena.
        dest = request.headers.get("Sec-Fetch-Dest", "").lower()
        if dest == "iframe":
            return True
        if dest == "document":
            # Navegación top-level inequívoca: no estamos embebidos, y además
            # invalida cualquier cookie de respaldo que hubiera quedado.
            return False

        # Capa 2: navegadores sin `Sec-Fetch-*`, o subrecursos.
        if request.GET.get(EMBED_QUERY_PARAM) == "1":
            return True
        return request.COOKIES.get(EMBED_COOKIE) == "1"

    # -- redirect al shell -------------------------------------------------

    def _maybe_redirect_to_shell(self, request, *, embedded: bool, standalone: bool):
        if embedded or standalone:
            return None
        if not getattr(settings, "PALDACA_EMBED_REDIRECT_TO_SHELL", False):
            return None
        if request.method != "GET":
            return None
        # Sin `Sec-Fetch-Dest: document` no podemos afirmar que sea top-level;
        # ante la duda no se redirige, para no dejar a nadie atrapado.
        if request.headers.get("Sec-Fetch-Dest", "").lower() != "document":
            return None

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None

        excluded = getattr(
            settings, "PALDACA_EMBED_EXCLUDED_PREFIXES", DEFAULT_EXCLUDED_PREFIXES
        )
        if any(request.path.startswith(prefix) for prefix in excluded):
            return None

        portal = _portal_origin()
        shell_path = (getattr(settings, "PALDACA_SHELL_PATH", "") or "").rstrip("/")
        if not portal or not shell_path:
            return None

        return redirect(f"{portal}{shell_path}{request.get_full_path()}")

    # -- cabeceras y cookies ----------------------------------------------

    def _apply_frame_headers(self, response) -> None:
        ancestors = getattr(settings, "PALDACA_FRAME_ANCESTORS", "").strip()
        if not ancestors:
            return

        # `X-Frame-Options` no sabe de listas de orígenes: `SAMEORIGIN` no vale
        # (cpaldaca.com y activos.cpaldaca.com son orígenes distintos) y
        # `ALLOW-FROM` está obsoleto y lo ignoran Chrome y Safari. La única
        # cabecera que expresa "solo el Portal puede enmarcarme" es CSP.
        # Se elimina explícitamente porque, si quedara, algún navegador o proxy
        # podría seguir aplicándola y bloquear el iframe.
        if response.has_header("X-Frame-Options"):
            del response["X-Frame-Options"]

        if not response.has_header("Content-Security-Policy"):
            response["Content-Security-Policy"] = f"frame-ancestors {ancestors}"

    def _apply_cookies(self, request, response, embedded: bool, standalone: bool):
        secure = bool(getattr(settings, "SESSION_COOKIE_SECURE", False))

        if standalone:
            if request.COOKIES.get(STANDALONE_COOKIE) != "1":
                response.set_cookie(
                    STANDALONE_COOKIE,
                    "1",
                    path="/",
                    samesite="Lax",
                    secure=secure,
                    httponly=True,
                )
        elif request.GET.get(STANDALONE_QUERY_PARAM) is not None:
            response.delete_cookie(STANDALONE_COOKIE, path="/")

        if embedded:
            if request.COOKIES.get(EMBED_COOKIE) != "1":
                response.set_cookie(
                    EMBED_COOKIE,
                    "1",
                    path="/",
                    samesite="Lax",
                    secure=secure,
                    httponly=True,
                )
        elif request.headers.get("Sec-Fetch-Dest", "").lower() == "document":
            # Top-level confirmado: la cookie de respaldo ya no aplica. Sin este
            # borrado, abrir el subdominio en una pestaña seguiría pareciendo
            # embebido y el satélite se quedaría sin sidebar.
            if request.COOKIES.get(EMBED_COOKIE) is not None:
                response.delete_cookie(EMBED_COOKIE, path="/")

        return response
