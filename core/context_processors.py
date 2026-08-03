import os
from pathlib import Path

from django.conf import settings

from .embed import is_embedded


def _is_local_stack() -> bool:
    """True solo en máquina de desarrollo (existe ActivosPALDACA/dev.env)."""
    return (Path(settings.BASE_DIR) / "dev.env").exists()


def _nav_asset_base() -> str:
    """Origen de paldaca-nav.{css,js}.

    Por defecto siempre https://cpaldaca.com para que el sidebar no dependa de
    que el Portal local (:8000) esté levantado (evita ERR_CONNECTION_REFUSED).

    Override local del bundle: PALDACA_NAV_ASSET_BASE=http://localhost:8000
    """
    override = (os.getenv("PALDACA_NAV_ASSET_BASE") or "").strip().rstrip("/")
    if override:
        return override
    return "https://cpaldaca.com"


def paldaca_urls(request):
    asset_base = _nav_asset_base()
    local = _is_local_stack()
    # Fuente unica: el mismo valor que usa core/embed.py como targetOrigin de
    # postMessage. Si divergieran, el shell descartaria en silencio todos los
    # mensajes del satelite y el overlay de carga se quedaria colgado.
    portal_url = settings.PALDACA_PORTAL_URL
    api_base = (
        (os.getenv("PALDACA_API_BASE") or "").strip().rstrip("/")
        or ("http://localhost:8000/api" if local else "https://api.cpaldaca.com/api")
    )
    return {
        "paldaca_sso_login_url": settings.PALDACA_SSO_LOGIN_URL,
        "paldaca_sso_logout_url": settings.PALDACA_SSO_LOGOUT_URL,
        "paldaca_nav_css": f"{asset_base}/static/paldaca-nav.css",
        "paldaca_nav_js": f"{asset_base}/static/paldaca-nav.js",
        "paldaca_embed_css": f"{asset_base}/static/paldaca-embed.css",
        "paldaca_nav_api_base": api_base,
        "paldaca_nav_portal_url": portal_url,
        "paldaca_nav_logo_full": f"{portal_url}/images/logo%20blanco.png",
        "paldaca_nav_logo_compact": f"{portal_url}/images/logo%20blanco%20recortado.png",
        "paldaca_nav_current_app": settings.PALDACA_MODULO_CODIGO,
        "paldaca_embedded": is_embedded(request),
    }
