#!/bin/sh
set -eu

if [ -z "${DATABASE_URL:-}" ]; then
    echo "[worker] ERRO: DATABASE_URL não está configurada."
    exit 1
fi

echo "[worker] Aguardando PostgreSQL..."
python docker/wait_for_database.py

echo "[worker] Iniciando worker..."
exec "$@"
