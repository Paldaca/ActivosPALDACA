import os
from pathlib import Path

import dj_database_url
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


def _mysql_config(*, defaults: dict | None = None) -> dict:
    defaults = defaults or {}
    return {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.getenv("MYSQL_DB", defaults.get("NAME", "paldaca_db")),
            "USER": os.getenv("MYSQL_USER", defaults.get("USER", "RAG")),
            "PASSWORD": os.getenv("MYSQL_PASSWORD", defaults.get("PASSWORD", "12345")),
            "HOST": os.getenv("MYSQL_HOST", defaults.get("HOST", "localhost")),
            "PORT": os.getenv("MYSQL_PORT", "") or defaults.get("PORT", "3306"),
        }
    }


# Local / SSO con Portal: MySQL vía MYSQL_* (dev.env o key.env local).
DATABASEDES = DATABASESDESARROLLO = _mysql_config()

# Producción Namecheap: defaults históricos; key.env puede sobreescribir MYSQL_*.
DATABASEPROD = DATABASESPRODUCCION = _mysql_config(
    defaults={
        "NAME": "ssapmcco_PALDACA_DB",
        "USER": "ssapmcco_ADMIN",
        "PASSWORD": "ADMINPALDACA12345",
        "HOST": "localhost",
        "PORT": "3306",
    }
)


def get_databases() -> dict:
    """Usa DATABASE_URL (MySQL compartida en Coolify) si existe; si no, MYSQL_*."""
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        return DATABASEDES if _DEV_ENV.exists() else DATABASEPROD

    ssl_require = os.getenv("DATABASE_SSL_REQUIRE", "false").lower() == "true"
    conn_max_age = int(os.getenv("DATABASE_CONN_MAX_AGE", "600"))
    config = dj_database_url.parse(
        database_url,
        conn_max_age=conn_max_age,
        conn_health_checks=True,
        ssl_require=ssl_require,
        engine="django.db.backends.mysql",
    )
    config["ENGINE"] = "django.db.backends.mysql"
    config.setdefault("OPTIONS", {})
    config["OPTIONS"].setdefault("charset", "utf8mb4")
    return {"default": config}
