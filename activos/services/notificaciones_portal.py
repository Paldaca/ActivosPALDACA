"""Emite eventos al bus de notificaciones de Portal-Paldaca.

Llamada server-to-server firmada con un HMAC (clave propia del modulo si hay
PALDACA_NOTIF_SECRET; si no, derivada de DJANGO_SECRET_KEY, esquema legado)
(misma funcion que backend/notificaciones/firma.py del Portal). No necesita la
sesion de ningun usuario, asi que sirve igual desde una vista que desde un cron.

Nunca lanza: si el Portal no responde se registra y el guardado local sigue.
"""

import hashlib
import hmac
import json
import logging
import time
import urllib.error
import urllib.request

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 4
#: El User-Agent por defecto de urllib ("Python-urllib/3.x") lo bloquea
#: Cloudflare delante del Portal (error 1010, 403 antes de llegar a Django).
USER_AGENT = "PALDACA-Activos/1.0"
_SAL = b"paldaca.notificaciones.v1:"


def _secreto() -> str:
    """Secreto PROPIO de este modulo (`PALDACA_NOTIF_SECRET`, >= 32 caracteres; con
    varios separados por coma firma el primero) o, si no esta, el esquema legado
    derivado de DJANGO_SECRET_KEY. El Portal aplica la misma regla de longitud, asi
    que uno mas corto se ignora en los dos lados."""
    propio = _secreto_propio()
    return propio if len(propio) >= 32 else settings.SECRET_KEY


def _secreto_propio() -> str:
    return (getattr(settings, "PALDACA_NOTIF_SECRET", "") or "").split(",")[0].strip()


def huella(secreto: str) -> str:
    """8 hex del SHA-256 del secreto: misma huella que imprime el Portal
    (`diagnosticar_firmas`, `NOTIF_FIRMA_RECHAZADA`) para comparar sin revelarlo."""
    return hashlib.sha256(secreto.encode()).hexdigest()[:8]


def esquema_firma() -> tuple[str, str]:
    """(`propio` | `legado`, huella del secreto con el que se firma)."""
    propio = _secreto_propio()
    if len(propio) >= 32:
        return "propio", huella(propio)
    return "legado", huella(settings.SECRET_KEY)


def _contexto_firma() -> str:
    esquema, hue = esquema_firma()
    return f"esquema={esquema} huella={hue}"


def firmar(cuerpo: bytes, cliente: str, timestamp: str) -> str:
    clave = hashlib.sha256(_SAL + _secreto().encode()).digest()
    mensaje = f"{timestamp}.{cliente}.".encode() + cuerpo
    return hmac.new(clave, mensaje, hashlib.sha256).hexdigest()


def url_en_portal(ruta: str) -> str:
    """Deep link a una pantalla de este modulo dentro del shell del Portal."""
    return f"{settings.PALDACA_PORTAL_URL}{settings.PALDACA_SHELL_PATH}{ruta}"


def emitir_evento(*, codigo, titulo, cuerpo, payload=None, emisor=None, clave_agrupacion="") -> bool:
    """
    `clave_agrupacion`: identidad estable del hecho (ej. "resumen_semanal:2026-09-14").
    El Portal actualiza el Evento vivo con esa clave en vez de crear uno
    nuevo si ya existe -- protege contra que el despachador corra dos veces
    en la misma ventana horaria y duplique un aviso agregado (ver riesgo en
    docs/plan-notificaciones.md §6). Vacía por defecto: cada llamada crea un
    evento nuevo, que es lo correcto para hechos puntuales.
    """
    if not settings.PALDACA_NOTIFICACIONES_ACTIVAS:
        logger.info("NOTIFICACION_OMITIDA | codigo=%s PALDACA_NOTIFICACIONES_ACTIVAS=false", codigo)
        return False
    cliente = settings.PALDACA_MODULO_CODIGO
    datos = {
        "codigo": codigo,
        "titulo": titulo[:200],
        "cuerpo": cuerpo,
        "payload": payload or {},
    }
    if clave_agrupacion:
        datos["clave_agrupacion"] = clave_agrupacion[:120]
    if getattr(emisor, "pk", None) is not None:
        datos["emisor_id"] = emisor.pk
    cuerpo_json = json.dumps(datos).encode()
    timestamp = str(int(time.time()))
    peticion = urllib.request.Request(
        f"{settings.PALDACA_PORTAL_API_URL}/notificaciones/eventos/",
        data=cuerpo_json,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "X-Paldaca-Client": cliente,
            "X-Paldaca-Timestamp": timestamp,
            "X-Paldaca-Signature": firmar(cuerpo_json, cliente, timestamp),
        },
    )
    try:
        with urllib.request.urlopen(peticion, timeout=TIMEOUT_SEGUNDOS):
            pass
    except urllib.error.HTTPError as exc:
        logger.warning(
            "NOTIFICACION_RECHAZADA | codigo=%s status=%s %s url=%s detalle=%s",
            codigo,
            exc.code,
            _contexto_firma(),
            peticion.full_url,
            exc.read()[:300],
        )
        return False
    except Exception as exc:
        logger.warning(
            "NOTIFICACION_NO_ENVIADA | codigo=%s url=%s error=%s", codigo, peticion.full_url, exc
        )
        return False
    logger.info("NOTIFICACION_EMITIDA | codigo=%s %s", codigo, _contexto_firma())
    return True


def emitir_al_confirmar(**kwargs) -> None:
    """Emite cuando la transaccion confirma: un rollback no deja avisos fantasma."""
    transaction.on_commit(lambda: emitir_evento(**kwargs))


def obtener_config_tipo(codigo: str) -> dict | None:
    """Lee la config vigente de un tipo propio (ej. `umbral_dias`) via GET firmado.

    `None` si las notificaciones estan apagadas, el Portal no responde, o el
    tipo no existe/no es nuestro (403) -- el llamador siempre debe tener un
    default local para ese caso, esto nunca bloquea la regla que lo usa.
    """
    if not settings.PALDACA_NOTIFICACIONES_ACTIVAS:
        return None
    cliente = settings.PALDACA_MODULO_CODIGO
    timestamp = str(int(time.time()))
    peticion = urllib.request.Request(
        f"{settings.PALDACA_PORTAL_API_URL}/notificaciones/tipos/{codigo}/config/",
        method="GET",
        headers={
            "User-Agent": USER_AGENT,
            "X-Paldaca-Client": cliente,
            "X-Paldaca-Timestamp": timestamp,
            "X-Paldaca-Signature": firmar(b"", cliente, timestamp),
        },
    )
    try:
        with urllib.request.urlopen(peticion, timeout=TIMEOUT_SEGUNDOS) as respuesta:
            return json.loads(respuesta.read())
    except urllib.error.HTTPError as exc:
        logger.warning(
            "CONFIG_TIPO_RECHAZADA | codigo=%s status=%s %s url=%s detalle=%s",
            codigo,
            exc.code,
            _contexto_firma(),
            peticion.full_url,
            exc.read()[:300],
        )
        return None
    except Exception as exc:
        logger.warning(
            "CONFIG_TIPO_NO_DISPONIBLE | codigo=%s url=%s error=%s", codigo, peticion.full_url, exc
        )
        return None
