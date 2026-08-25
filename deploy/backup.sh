#!/bin/sh
# Dump diário do Postgres com retenção de 30 dias. Roda no container `backup`.
set -e
while true; do
  STAMP=$(date +%Y%m%d_%H%M)
  pg_dump -h db -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-sistema_interno}" -Fc -f "/backups/sistema_${STAMP}.dump"
  find /backups -name "sistema_*.dump" -mtime +30 -delete
  echo "backup ${STAMP} ok"
  sleep 86400
done
