"""Diagnostica la comunicacion Activos -> Nomina paso a paso.

El cliente normal (`nomina_directorio.py`) degrada a "lista vacia" ante
cualquier fallo, asi que en produccion solo se ve un combo sin resultados.
Este comando hace la MISMA llamada pero muestra que respondio Nomina y que
revisar.

    python manage.py probar_nomina --cookie <valor de paldaca_sessionid>

El valor de la cookie se copia del navegador (DevTools > Application >
Cookies) con la sesion iniciada. Correrlo dentro del contenedor de Activos
(terminal de Coolify) para probar la red real entre ambos servicios.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand

from activos.services.nomina_directorio import TIMEOUT_SEGUNDOS, USER_AGENT

PISTAS = {
    301: "Redireccion: la URL usa http:// y Nomina fuerza https (SECURE_SSL_REDIRECT), o falta/sobra una barra. Usa https:// en PALDACA_NOMINA_API_URL.",
    302: "Redireccion: revisa que la URL sea exactamente la publica de Nomina.",
    400: "Nomina rechazo el Host: agrega el dominio usado en PALDACA_NOMINA_API_URL a DJANGO_ALLOWED_HOSTS de Nomina.",
    401: "Nomina no pudo validar la cookie contra el Portal: cookie vencida/incorrecta, o Nomina no alcanza al Portal (PALDACA_PORTAL_API_URL de Nomina).",
    403: "Rechazado. Puede ser: (a) PALDACA_DIRECTORIO_SATELITES_AUTORIZADOS de Nomina no incluye 'activos'; (b) el usuario no tiene el modulo 'activos' en el Portal; (c) un WAF/Cloudflare bloqueando la peticion (mira si el cuerpo es HTML).",
    404: "No existe la ruta: Nomina no tiene desplegado el endpoint nuevo (falta redeploy de Nomina con el commit) o a PALDACA_NOMINA_API_URL le falta/sobra '/api'.",
    503: "Nomina no pudo contactar al Portal para validar la cookie (PALDACA_PORTAL_API_URL de Nomina).",
}


class _SinRedireccion(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Command(BaseCommand):
    help = "Prueba la llamada Activos -> Nomina y explica que falla."

    def add_arguments(self, parser):
        parser.add_argument("--cookie", required=True, help="Valor de la cookie paldaca_sessionid.")
        parser.add_argument("--q", default="", help="Texto de busqueda (opcional).")

    def handle(self, *args, cookie, q, **options):
        base = settings.PALDACA_NOMINA_API_URL
        url = f"{base}/empleados/directorio/asignables/?{urllib.parse.urlencode({'q': q, 'page': 1})}"
        self.stdout.write(f"PALDACA_NOMINA_API_URL = {base}")
        self.stdout.write(f"PALDACA_MODULO_CODIGO  = {settings.PALDACA_MODULO_CODIGO} (va en X-Paldaca-Client)")
        self.stdout.write(f"GET {url}\n")

        peticion = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
                "X-Paldaca-Client": settings.PALDACA_MODULO_CODIGO,
                "Cookie": f"{settings.SESSION_COOKIE_NAME}={cookie}",
            },
        )
        opener = urllib.request.build_opener(_SinRedireccion)
        inicio = time.time()
        try:
            with opener.open(peticion, timeout=TIMEOUT_SEGUNDOS) as r:
                estado, cuerpo, cabeceras = r.status, r.read(), r.headers
        except urllib.error.HTTPError as exc:
            estado, cuerpo, cabeceras = exc.code, exc.read(), exc.headers
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"SIN RESPUESTA ({type(exc).__name__}): {exc}"))
            self.stdout.write(
                "Causas tipicas: DNS/red entre contenedores, dominio mal escrito, "
                f"o Nomina caida. Timeout usado: {TIMEOUT_SEGUNDOS}s."
            )
            return

        ms = int((time.time() - inicio) * 1000)
        self.stdout.write(f"HTTP {estado} en {ms} ms  (Server: {cabeceras.get('Server', '?')})")
        if cabeceras.get("Location"):
            self.stdout.write(f"Location: {cabeceras['Location']}")
        texto = cuerpo.decode("utf-8", "replace")
        self.stdout.write(f"Cuerpo: {texto[:300]}\n")

        if estado == 200:
            try:
                n = len(json.loads(texto).get("empleados", []))
            except ValueError:
                self.stdout.write(self.style.ERROR("200 pero NO es JSON: algo intermedio (proxy/WAF) responde en lugar de Nomina."))
                return
            if n:
                self.stdout.write(self.style.SUCCESS(f"OK: Nomina devolvio {n} empleado(s). La comunicacion funciona."))
            else:
                self.stdout.write(self.style.WARNING(
                    "Comunicacion OK pero 0 empleados: en Nomina ninguno esta activo y vinculado al Portal "
                    "(Empleados > Vinculos)."
                ))
            return
        if texto.lstrip().startswith("<"):
            self.stdout.write(self.style.ERROR(
                f"HTTP {estado} con cuerpo HTML: la peticion NO llego al endpoint JSON. "
                "Lo mas probable es que PALDACA_NOMINA_API_URL no termine en '/api' "
                "(cae en las paginas de Nomina para navegador) o que un WAF/Cloudflare "
                "responda en lugar de Nomina."
            ))
            return
        self.stdout.write(self.style.ERROR(PISTAS.get(estado, "Respuesta inesperada de Nomina.")))
