FROM python:3.13-slim

# No escribe ficheros .pyc y no bufferiza stdout/stderr: los logs de la
# aplicación aparecen en `docker compose logs` en el momento en que se emiten,
# no cuando se llena el buffer.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /code

# Las dependencias se copian e instalan antes que el código: mientras
# requirements.txt no cambie, Docker reutiliza esta capa y no reinstala nada
# en cada rebuild.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# cron lo usa el servicio payment-plans-cron (docker-compose.yml) para
# materializar a diario los planes de pago vencidos (payment_plans.md §5).
# El servicio api no lo arranca, pero comparte esta misma imagen.
RUN apt-get update \
    && apt-get install -y --no-install-recommends cron \
    && rm -rf /var/lib/apt/lists/*

# Usuario sin privilegios: si alguien consigue ejecutar código dentro del
# contenedor, no lo hace como root.
RUN useradd --create-home --uid 1000 appuser

COPY --chown=appuser:appuser . .
RUN chmod +x entrypoint.sh docker/cron-entrypoint.sh

# /etc/cron.d en vez de `crontab -u`: el propio fichero declara qué usuario
# ejecuta la línea, así cron puede arrancar como root y aun así correr el
# job como appuser.
COPY docker/payment-plans-cron /etc/cron.d/payment-plans-cron
RUN chmod 0644 /etc/cron.d/payment-plans-cron

USER appuser

ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
