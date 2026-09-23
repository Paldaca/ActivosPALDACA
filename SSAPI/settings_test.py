"""
Ajustes para pruebas automatizadas (pytest-django).
Usa SQLite en memoria para no depender de PostgreSQL/MySQL ni de SSAPI/db.py en CI/local.
"""
from .settings import *  # noqa: F403, F401

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Ningun test sale a la red: los que prueban la emision la simulan.
PALDACA_NOTIFICACIONES_ACTIVAS = False
