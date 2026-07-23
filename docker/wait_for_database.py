"""Wait for PostgreSQL to become available using psycopg 3.

Uses DATABASE_URL as the single source of truth. Never prints credentials.
"""
import os
import sys
import time
from urllib.parse import urlparse

import psycopg

MAX_ATTEMPTS = int(os.getenv("DB_WAIT_MAX_ATTEMPTS", "60"))
INTERVAL_SECONDS = int(os.getenv("DB_WAIT_INTERVAL_SECONDS", "2"))
CONNECT_TIMEOUT_SECONDS = int(os.getenv("DB_CONNECT_TIMEOUT_SECONDS", "5"))
DNS_ERROR_MARKERS = (
    "failed to resolve host",
    "name or service not known",
    "temporary failure in name resolution",
)


def _mask_url(database_url: str) -> str:
    parsed = urlparse(database_url)
    host = parsed.hostname or "?"
    port = f":{parsed.port}" if parsed.port else ""
    dbname = parsed.path.lstrip("/") or "?"
    return f"postgresql://***:***@{host}{port}/{dbname}"


def _normalize_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql://", 1)
    if not database_url.startswith("postgresql://"):
        raise ValueError(
            f"DATABASE_URL must start with 'postgresql://' or 'postgres://'. "
            f"Received: {_mask_url(database_url) if '://' in database_url else database_url[:30]}"
        )
    return database_url


def _is_dns_error(error: str) -> bool:
    lowered = error.lower()
    return any(marker in lowered for marker in DNS_ERROR_MARKERS)


def wait_for_database(database_url: str) -> None:
    conn_str = _normalize_url(database_url)
    masked = _mask_url(conn_str)
    last_error = ""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with psycopg.connect(
                conn_str,
                connect_timeout=CONNECT_TIMEOUT_SECONDS,
            ) as conn, conn.cursor() as cur:
                cur.execute("SELECT 1")
            print(f"[db-wait] PostgreSQL disponível ({masked})")
            return
        except psycopg.OperationalError as exc:
            last_error = str(exc).strip().replace("\n", " | ")
            print(
                f"[db-wait] Tentativa {attempt}/{MAX_ATTEMPTS}: "
                f"{masked} indisponível. "
                f"Motivo: {last_error[:120]}"
            )
            if attempt == 1 and _is_dns_error(last_error):
                print(
                    "[db-wait] DIAGNÓSTICO: o hostname do PostgreSQL não resolve. "
                    "No Coolify, habilite 'Connect to Predefined Network' na "
                    "aplicação e substitua DATABASE_URL pela Internal URL atual "
                    "exibida no recurso PostgreSQL."
                )
        except Exception as exc:
            last_error = str(exc).strip().replace("\n", " | ")
            print(
                f"[db-wait] Tentativa {attempt}/{MAX_ATTEMPTS}: "
                f"erro inesperado ao conectar em {masked}: "
                f"{last_error[:120]}"
            )

        if attempt < MAX_ATTEMPTS:
            time.sleep(INTERVAL_SECONDS)

    print(
        f"[db-wait] ERRO: PostgreSQL não ficou disponível após "
        f"{MAX_ATTEMPTS} tentativas ({masked}). "
        f"Último erro: {last_error[:200]}"
    )
    if _is_dns_error(last_error):
        print(
            "[db-wait] AÇÃO: revise a rede gerenciada pelo Coolify e a Internal "
            "URL do banco; aumentar tentativas não corrige falha de DNS."
        )
    sys.exit(1)


def main() -> None:
    try:
        database_url = os.environ.get("DATABASE_URL", "").strip()
    except Exception:
        database_url = ""

    if not database_url:
        print("[db-wait] ERRO: DATABASE_URL não está configurada. Esta variável é obrigatória.")
        sys.exit(1)

    try:
        wait_for_database(database_url)
    except ValueError as exc:
        print(f"[db-wait] ERRO: {exc}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[db-wait] Interrompido pelo usuário.")
        sys.exit(1)


if __name__ == "__main__":
    main()
