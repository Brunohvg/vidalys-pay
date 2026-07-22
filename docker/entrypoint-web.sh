#!/bin/sh
set -eu

echo "[web] Validando configuração..."

if [ -z "${SECRET_KEY:-}" ]; then
    echo "[web] ERRO: SECRET_KEY não está configurada."
    exit 1
fi

if [ -z "${DATABASE_URL:-}" ]; then
    echo "[web] ERRO: DATABASE_URL não está configurada."
    exit 1
fi

echo "[web] Aguardando PostgreSQL..."
python docker/wait_for_database.py

echo "[web] Executando migrations..."
python manage.py migrate --noinput

echo "[web] Coletando arquivos estáticos..."
python manage.py collectstatic --noinput

echo "[web] Iniciando aplicação..."
exec "$@"
