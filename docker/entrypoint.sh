#!/bin/bash
set -e

echo "Aguardando PostgreSQL..."
while ! pg_isready -h "${DB_HOST:-db}" -p "${DB_PORT:-5432}" -U "${POSTGRES_USER:-vidalys_pay}" -q; do
    sleep 1
done
echo "PostgreSQL pronto."

echo "Executando migrations..."
python manage.py migrate --noinput

echo "Coletando arquivos estáticos..."
python manage.py collectstatic --noinput

echo "Iniciando aplicação..."
exec "$@"
