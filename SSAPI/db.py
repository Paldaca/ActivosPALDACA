import os
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent
_KEY_ENV = _REPO_ROOT / "key.env"
_DEV_ENV = _REPO_ROOT / "dev.env"

if _KEY_ENV.exists():
    load_dotenv(_KEY_ENV)
if _DEV_ENV.exists():
    load_dotenv(_DEV_ENV, override=True)
else:
    load_dotenv()

# Local / SSO con Portal: MySQL vía MYSQL_* (dev.env o key.env local).
DATABASEDES = DATABASESDESARROLLO = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("MYSQL_DB", "paldaca_db"),
        "USER": os.getenv("MYSQL_USER", "RAG"),
        "PASSWORD": os.getenv("MYSQL_PASSWORD", "12345"),
        "HOST": os.getenv("MYSQL_HOST", "localhost"),
        "PORT": os.getenv("MYSQL_PORT", "3306"),
    }
}

# Producción Namecheap: defaults históricos; key.env puede sobreescribir MYSQL_*.
DATABASEPROD = DATABASESPRODUCCION = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("MYSQL_DB", "ssapmcco_PALDACA_DB"),
        "USER": os.getenv("MYSQL_USER", "ssapmcco_ADMIN"),
        "PASSWORD": os.getenv("MYSQL_PASSWORD", "ADMINPALDACA12345"),
        "HOST": os.getenv("MYSQL_HOST", "localhost"),
        "PORT": os.getenv("MYSQL_PORT", "") or "3306",
    }
}
