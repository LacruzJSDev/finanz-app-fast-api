#!/bin/sh
set -e

# Las migraciones se aplican al arrancar el contenedor, no en el build: en el
# build no hay base de datos a la que conectarse. Alembic es idempotente, así
# que en un arranque sin migraciones nuevas esto no hace nada.
echo "Aplicando migraciones..."
alembic upgrade head

# exec sustituye el proceso del script por el comando final, en vez de dejarlo
# como hijo. Así uvicorn recibe directamente las señales de Docker (SIGTERM al
# hacer `docker compose down`) y puede cerrar de forma ordenada.
exec "$@"
