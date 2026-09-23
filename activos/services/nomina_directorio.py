"""Consulta el directorio saliente de empleados de Nomina PALDACA.

Nomina es un satelite FEDERADO (BD propia, ver
Portal-Paldaca/docs/PALDACA_SUITE/CONTRATO_SSO_FEDERADO.md): no hay forma de
hacer JOIN entre `activos_activo` y `Nomina_empleados`. En su lugar se
reutiliza el MISMO patron de cookie-forwarding que Nomina ya usa para hablar
con el Portal (`paldaca_sso/client.py` en Nomina): esta llamada reenvia
UNICAMENTE la cookie de sesion del operador que ya trae la peticion entrante
(Activos comparte cookie y BD con el Portal), nunca credenciales propias de
Activos. El endpoint de Nomina valida esa cookie contra el Portal por su
cuenta -- no hay ningun secreto nuevo compartido entre Activos y Nomina.

Nunca lanza: si Nomina no responde se registra y se degrada a "sin
resultados" (mismo criterio que notificaciones_portal.py). Un selector de
personas que tarda o falla no puede tumbar el formulario de un activo.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 3


def buscar_empleados_asignables(request, *, q: str = "", page: int = 1) -> dict:
    """Empleados activos de Nomina vinculados al Portal, para el combo remoto.

    Devuelve siempre `{'results': [{'id', 'text'}], 'has_more': bool}` --
    la misma forma que ya consume `activos-ui.js` -- vacio si Nomina no
    responde, para que el llamador no tenga que distinguir "sin resultados"
    de "Nomina caida".
    """
    cookie_nombre = settings.SESSION_COOKIE_NAME
    cookie_valor = request.COOKIES.get(cookie_nombre)
    if not cookie_valor:
        # Sin cookie del Portal no hay con que autenticar la consulta ante
        # Nomina; ocurre solo si algo raro paso con la sesion (no debería,
        # las vistas que llegan aqui ya exigen login).
        logger.warning("NOMINA_DIRECTORIO_SIN_COOKIE")
        return {"results": [], "has_more": False}

    query = urllib.parse.urlencode({"q": q, "page": page})
    url = f"{settings.PALDACA_NOMINA_API_URL}/empleados/directorio/asignables/?{query}"
    peticion = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "X-Paldaca-Client": settings.PALDACA_MODULO_CODIGO,
            "Cookie": f"{cookie_nombre}={cookie_valor}",
        },
    )
    try:
        with urllib.request.urlopen(peticion, timeout=TIMEOUT_SEGUNDOS) as respuesta:
            datos = json.loads(respuesta.read())
    except urllib.error.HTTPError as exc:
        logger.warning(
            "NOMINA_DIRECTORIO_RECHAZADO | status=%s detalle=%s",
            exc.code, exc.read()[:300],
        )
        return {"results": [], "has_more": False}
    except Exception as exc:
        logger.warning("NOMINA_DIRECTORIO_NO_DISPONIBLE | error=%s", exc)
        return {"results": [], "has_more": False}

    empleados = datos.get("empleados") or []
    return {
        "results": [
            {"id": e["portal_user_id"], "text": _etiqueta(e)}
            for e in empleados
            if e.get("portal_user_id")
        ],
        "has_more": bool(datos.get("has_more")),
    }


def _etiqueta(empleado: dict) -> str:
    nombre = (empleado.get("nombre_completo") or "").strip()
    cargo = (empleado.get("cargo") or "").strip()
    return f"{nombre} — {cargo}" if cargo else nombre
