"""Cliente hacia el directorio saliente de Nomina (activos/services/nomina_directorio.py).

Nunca se golpea una Nomina real: se sustituye `urllib.request.urlopen`, igual
que ya hace `test_notificaciones.py` con el bus del Portal.
"""

import json
import urllib.error
from io import BytesIO
from unittest import mock

from django.test import RequestFactory

from activos.services.nomina_directorio import buscar_empleados_asignables


def _request_con_cookie(cookie="abc123"):
    request = RequestFactory().get("/")
    if cookie is not None:
        request.COOKIES["paldaca_sessionid"] = cookie
    return request


def _respuesta_json(payload):
    contexto = mock.MagicMock()
    contexto.read.return_value = json.dumps(payload).encode()
    contexto.__enter__.return_value = contexto
    contexto.__exit__.return_value = False
    return contexto


def test_sin_cookie_no_llama_a_nomina():
    request = _request_con_cookie(cookie=None)
    with mock.patch("urllib.request.urlopen") as urlopen:
        resultado = buscar_empleados_asignables(request, q="ana")
    urlopen.assert_not_called()
    assert resultado == {"results": [], "has_more": False}


def test_traduce_empleados_de_nomina_al_contrato_del_combo():
    request = _request_con_cookie()
    payload_nomina = {
        "empleados": [
            {
                "portal_user_id": 7,
                "nombre_completo": "Ana Soto",
                "cargo": "Analista",
                "cedula": "V-1",
            },
            {
                # Sin portal_user_id: no puede guardarse en usuario_asignado,
                # se descarta aunque Nomina lo haya devuelto.
                "portal_user_id": None,
                "nombre_completo": "Sin Vinculo",
                "cargo": "Analista",
                "cedula": "V-2",
            },
        ],
        "has_more": True,
    }
    with mock.patch(
        "urllib.request.urlopen", return_value=_respuesta_json(payload_nomina)
    ) as urlopen:
        resultado = buscar_empleados_asignables(request, q="ana", page=2)

    assert resultado == {
        "results": [{"id": 7, "text": "Ana Soto — Analista"}],
        "has_more": True,
    }
    peticion = urlopen.call_args.args[0]
    assert "q=ana" in peticion.full_url
    assert "page=2" in peticion.full_url
    assert peticion.headers["X-paldaca-client"] == "activos"
    assert peticion.headers["Cookie"] == "paldaca_sessionid=abc123"


def test_nomina_no_disponible_degrada_a_vacio():
    request = _request_con_cookie()
    error = urllib.error.URLError("timed out")
    with mock.patch("urllib.request.urlopen", side_effect=error):
        resultado = buscar_empleados_asignables(request, q="ana")
    assert resultado == {"results": [], "has_more": False}


def test_nomina_rechaza_la_peticion_degrada_a_vacio():
    request = _request_con_cookie()
    error = urllib.error.HTTPError(
        "http://nomina.test/api/empleados/directorio/asignables/",
        403,
        "Forbidden",
        {},
        BytesIO(b'{"detail": "Cliente no autorizado."}'),
    )
    with mock.patch("urllib.request.urlopen", side_effect=error):
        resultado = buscar_empleados_asignables(request, q="ana")
    assert resultado == {"results": [], "has_more": False}
