#!/bin/bash
set -e

echo "Aguardando PostgreSQL..."

# Tentar pg_isready, se não existir usar python para testar conexão
if command -v pg_isready &> /dev/null; then
    while ! pg_isready -h "${DB_HOST:-db}" -p "${DB_PORT:-5432}" -U "${POSTGRES_USER:-vidalys_pay}" -q 2>/dev/null; do
        sleep 1
    done
else
    # Fallback: usar Python para testar conexão
    while ! python -c "
import os
import psycopg2
try:
    conn = psycopg2.connect(os.environ.get('DATABASE_URL', ''))
    conn.close()
except:
    exit(1)
" 2>/dev/null; do
        sleep 1
    done
fi

echo "PostgreSQL pronto."

echo "Executando migrations..."
python manage.py migrate --noinput

echo "Coletando arquivos estáticos..."
python manage.py collectstatic --noinput

echo "Iniciando aplicação..."
exec "$@"
