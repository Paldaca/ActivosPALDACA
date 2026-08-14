#!/bin/sh
set -eu

PORT="${PORT:-8082}"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-3}"
GUNICORN_THREADS="${GUNICORN_THREADS:-2}"
GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-60}"

echo "Esperando MySQL..."
python - <<'PY'
import os
import sys
import time

import dj_database_url
import MySQLdb

url = os.environ.get("DATABASE_URL", "").strip()
if not url:
    print("DATABASE_URL no está definida.", file=sys.stderr)
    sys.exit(1)

cfg = dj_database_url.parse(url)
last_error = None
for attempt in range(1, 31):
    try:
        conn = MySQLdb.connect(
            host=cfg.get("HOST") or "localhost",
            port=int(cfg.get("PORT") or 3306),
            user=cfg.get("USER") or "",
            passwd=cfg.get("PASSWORD") or "",
            db=cfg.get("NAME") or "",
            connect_timeout=3,
            charset="utf8mb4",
        )
        conn.close()
        print("MySQL listo.")
        sys.exit(0)
    except Exception as exc:
        last_error = exc
        print(f"Esperando MySQL ({attempt}/30): {exc}")
        time.sleep(2)

print(f"No se pudo conectar a MySQL: {last_error}", file=sys.stderr)
sys.exit(1)
PY

echo "Aplicando migraciones..."
python manage.py migrate --noinput

echo "Recopilando estáticos..."
python manage.py collectstatic --noinput

echo "Arrancando Gunicorn en 0.0.0.0:${PORT}"
exec gunicorn SSAPI.wsgi:application \
  --bind "0.0.0.0:${PORT}" \
  --workers "${GUNICORN_WORKERS}" \
  --threads "${GUNICORN_THREADS}" \
  --timeout "${GUNICORN_TIMEOUT}" \
  --access-logfile - \
  --error-logfile - \
  --forwarded-allow-ips="*"
