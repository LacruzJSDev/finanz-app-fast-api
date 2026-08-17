#!/bin/sh
set -e

# cron no hereda el entorno del contenedor: el job del crontab (ver
# docker/payment-plans-cron) hace ". /etc/environment" antes de arrancar
# run_due.py, así que las variables tienen que quedar volcadas aquí,
# exportadas, para que el proceso python hijo también las herede.
printenv | sed -E 's/^([^=]+)=(.*)$/export \1="\2"/' > /etc/environment
chmod 644 /etc/environment

exec cron -f
