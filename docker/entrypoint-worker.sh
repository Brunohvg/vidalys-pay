#!/bin/sh
set -eu

if [ -z "${DATABASE_URL:-}" ]; then
    echo "[worker] ERRO: DATABASE_URL não está configurada."
    exit 1
fi

echo "[worker] Aguardando PostgreSQL..."
python docker/wait_for_database.py

echo "[worker] Executando verificações de produção..."
python manage.py check --deploy --fail-level ERROR

echo "[worker] Iniciando worker..."
exec "$@"
