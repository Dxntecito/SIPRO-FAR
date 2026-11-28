import os
from urllib.parse import urlparse
import pymysql
from pymysql.cursors import DictCursor

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENV_PATH = os.path.join(ROOT_DIR, ".env")


def load_env_file():
    """Carga variables desde .env sin requerir librerías externas."""
    if not os.path.exists(ENV_PATH):
        return
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


load_env_file()


def get_db_config() -> dict:
    """Soporta tanto MYSQL_URL / DATABASE_URL (Railway) como variables locales."""
    url = os.environ.get("MYSQL_URL") or os.environ.get("DATABASE_URL")
    if url and url.startswith("mysql"):
        parsed = urlparse(url)
        return {
            "host": parsed.hostname or "127.0.0.1",
            "port": parsed.port or 3306,
            "user": parsed.username or "root",
            "password": parsed.password or "",
            "database": (parsed.path or "/siprofar_db").lstrip("/"),
            "charset": "utf8mb4",
            "cursorclass": DictCursor,
            "autocommit": False,
        }
    return {
        "host": os.environ.get("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.environ.get("MYSQL_PORT", "3306")),
        "user": os.environ.get("MYSQL_USER", "root"),
        "password": os.environ.get("MYSQL_PASSWORD", ""),
        "database": os.environ.get("MYSQL_DB", "siprofar_db"),
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "autocommit": False,
    }


def get_connection():
    return pymysql.connect(**get_db_config())
