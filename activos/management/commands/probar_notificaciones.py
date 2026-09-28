"""Prueba la conexion firmada con el bus de notificaciones del Portal.

    python manage.py probar_notificaciones

Muestra la configuracion (URL, modulo, esquema de firma y HUELLA del secreto) y
hace una consulta firmada de SOLO LECTURA (`GET .../tipos/<codigo>/config/`),
que pasa por la misma autenticacion que la emision de avisos pero no crea
ninguno. Compara la huella con `python manage.py diagnosticar_firmas` del
Portal: si difieren, los dos lados tienen secretos distintos.
"""

import json
import time
import urllib.error
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from activos.services import notificaciones_portal as np
from activos.services.avisos import CODIGO_USUARIO_INACTIVO

DIAGNOSTICO = {
    403: (
        "Firma rechazada o tipo ajeno. Mira en el log del Portal la linea "
        "NOTIF_FIRMA_RECHAZADA: motivo=no_coincide -> huellas distintas (o el "
        "Portal no tiene PALDACA_NOTIF_SECRET_ACTIVOS y el legado esta cerrado); "
        "motivo=vencida -> reloj desfasado."
    ),
    404: "La ruta o el tipo no existen: revisa que PALDACA_PORTAL_API_URL termine en /api.",
    301: "Redireccion: usa https:// en PALDACA_PORTAL_API_URL.",
    302: "Redireccion: PALDACA_PORTAL_API_URL no apunta a la API (probablemente al SPA).",
}


class Command(BaseCommand):
    help = "Diagnostica la firma y la conexion con el bus de notificaciones del Portal."

    def add_arguments(self, parser):
        parser.add_argument("--codigo", default=CODIGO_USUARIO_INACTIVO)

    def handle(self, *args, codigo, **options):
        esquema, huella = np.esquema_firma()
        propio = np._secreto_propio()
        self.stdout.write(f"PALDACA_PORTAL_API_URL        = {settings.PALDACA_PORTAL_API_URL}")
        self.stdout.write(f"PALDACA_MODULO_CODIGO         = {settings.PALDACA_MODULO_CODIGO}")
        self.stdout.write(f"PALDACA_NOTIFICACIONES_ACTIVAS= {settings.PALDACA_NOTIFICACIONES_ACTIVAS}")
        self.stdout.write(f"Esquema de firma              = {esquema} (huella {huella})")
        if propio and len(propio) < 32:
            self.stdout.write(
                self.style.ERROR(
                    f"PALDACA_NOTIF_SECRET tiene {len(propio)} caracteres (<32): se IGNORA y se firma con el legado."
                )
            )
        elif not propio:
            self.stdout.write(self.style.WARNING("PALDACA_NOTIF_SECRET vacio: se firma con el legado (DJANGO_SECRET_KEY)."))
        if propio != propio.strip("'\""):
            self.stdout.write(self.style.ERROR("PALDACA_NOTIF_SECRET trae comillas: Coolify las guarda literales."))
        if not settings.PALDACA_NOTIFICACIONES_ACTIVAS:
            raise CommandError("Notificaciones apagadas: no se emite ningun aviso.")

        cliente = settings.PALDACA_MODULO_CODIGO
        timestamp = str(int(time.time()))
        url = f"{settings.PALDACA_PORTAL_API_URL}/notificaciones/tipos/{codigo}/config/"
        self.stdout.write(f"GET {url}")
        peticion = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Accept": "application/json",
                "X-Paldaca-Client": cliente,
                "X-Paldaca-Timestamp": timestamp,
                "X-Paldaca-Signature": np.firmar(b"", cliente, timestamp),
            },
        )
        try:
            with urllib.request.urlopen(peticion, timeout=np.TIMEOUT_SEGUNDOS) as respuesta:
                cuerpo = respuesta.read()
                status = respuesta.status
        except urllib.error.HTTPError as exc:
            detalle = exc.read()[:300].decode(errors="replace")
            raise CommandError(
                f"Portal respondio {exc.code}: {detalle}\n{DIAGNOSTICO.get(exc.code, '')}"
            ) from exc
        except Exception as exc:
            raise CommandError(f"Sin conexion con el Portal: {exc}") from exc

        try:
            datos = json.loads(cuerpo)
        except ValueError as exc:
            raise CommandError(
                f"Respuesta {status} no es JSON (¿la URL apunta al SPA?): {cuerpo[:200]!r}"
            ) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"OK {status}: firma aceptada ({esquema}). Tipo {datos.get('codigo')} activo={datos.get('activo')}. "
                "En el log del Portal debe aparecer NOTIF_FIRMA con este esquema."
            )
        )
