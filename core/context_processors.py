from django.conf import settings


def _nav_asset_base():
    if settings.DEBUG:
        return "http://localhost:8000"
    return "https://cpaldaca.com"


def paldaca_urls(request):
    asset_base = _nav_asset_base()
    portal_url = "http://localhost:5173" if settings.DEBUG else "https://cpaldaca.com"
    api_base = (
        "http://localhost:8000/api"
        if settings.DEBUG
        else "https://api.cpaldaca.com/api"
    )
    return {
        "paldaca_sso_login_url": settings.PALDACA_SSO_LOGIN_URL,
        "paldaca_sso_logout_url": settings.PALDACA_SSO_LOGOUT_URL,
        "paldaca_nav_css": f"{asset_base}/static/paldaca-nav.css",
        "paldaca_nav_js": f"{asset_base}/static/paldaca-nav.js",
        "paldaca_nav_api_base": api_base,
        "paldaca_nav_portal_url": portal_url,
        "paldaca_nav_logo_full": f"{portal_url}/images/logo%20blanco.png",
        "paldaca_nav_logo_compact": f"{portal_url}/images/logo%20blanco%20recortado.png",
        "paldaca_nav_current_app": "activos",
    }
