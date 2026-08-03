"""
Contrato de embebido en el shell del Portal (`paldaca-embed` v1).

Cubre lo que se rompe en silencio: si alguien repone `XFrameOptionsMiddleware`
o `X_FRAME_OPTIONS`, el modulo deja de cargar dentro de cpaldaca.com y el unico
sintoma es un area de trabajo en blanco, sin error en el servidor.
"""

import pytest
from django.test import override_settings


@pytest.mark.django_db
def test_dentro_del_iframe_emite_csp_y_no_bloquea_el_framing(client_auth):
    res = client_auth.get("/", headers={"sec-fetch-dest": "iframe"})

    assert res.status_code == 200
    assert "frame-ancestors" in res.headers.get("Content-Security-Policy", "")
    # X-Frame-Options no admite lista de origenes: si vuelve, el iframe muere.
    assert res.headers.get("X-Frame-Options") is None


@pytest.mark.django_db
def test_dentro_del_iframe_no_monta_el_nav_duplicado(client_auth):
    body = client_auth.get("/", headers={"sec-fetch-dest": "iframe"}).content.decode()

    assert "paldaca-nav-root" not in body
    assert "paldaca-embed.css" in body


@pytest.mark.django_db
def test_navegacion_top_level_conserva_el_nav_propio(client_auth):
    body = client_auth.get(
        "/", headers={"sec-fetch-dest": "document"}
    ).content.decode()

    assert "paldaca-nav-root" in body
    assert "paldaca-embed.css" not in body


@pytest.mark.django_db
def test_cookie_de_respaldo_mantiene_el_estado_sin_sec_fetch(client_auth):
    """Navegadores sin cabeceras `Sec-Fetch-*` (capa 2 de la deteccion)."""
    client_auth.get("/", headers={"sec-fetch-dest": "iframe"})

    body = client_auth.get("/").content.decode()

    assert "paldaca-embed.css" in body


@pytest.mark.django_db
def test_una_navegacion_top_level_invalida_la_cookie_de_respaldo(client_auth):
    """Sin esto, abrir el subdominio en una pestana seguiria pareciendo embebido."""
    client_auth.get("/", headers={"sec-fetch-dest": "iframe"})

    res = client_auth.get("/", headers={"sec-fetch-dest": "document"})

    assert res.cookies["paldaca_embed"]["max-age"] == 0
    assert "paldaca-nav-root" in res.content.decode()


@override_settings(PALDACA_EMBED_REDIRECT_TO_SHELL=True)
@pytest.mark.django_db
def test_acceso_directo_al_subdominio_redirige_al_shell(client_auth):
    res = client_auth.get("/mantenimientos/", headers={"sec-fetch-dest": "document"})

    assert res.status_code == 302
    assert res.headers["Location"].endswith("/activos/mantenimientos/")


@override_settings(PALDACA_EMBED_REDIRECT_TO_SHELL=True)
@pytest.mark.django_db
def test_el_redirect_al_shell_no_aplica_dentro_del_iframe(client_auth):
    """Redirigir aqui meteria el shell dentro del shell."""
    res = client_auth.get("/mantenimientos/", headers={"sec-fetch-dest": "iframe"})

    assert res.status_code == 200


@override_settings(PALDACA_EMBED_REDIRECT_TO_SHELL=True)
@pytest.mark.django_db
def test_valvula_de_escape_sirve_el_satelite_suelto(client_auth):
    res = client_auth.get(
        "/?paldaca_standalone=1", headers={"sec-fetch-dest": "document"}
    )

    assert res.status_code == 200
    assert "paldaca-nav-root" in res.content.decode()
