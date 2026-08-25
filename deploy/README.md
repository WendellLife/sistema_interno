# Deploy

```bash
cp .env.example .env            # preencha SECRET_KEY, POSTGRES_PASSWORD, ALLOWED_HOSTS, CSRF/CORS, e-mail
mkdir -p deploy/certs           # fullchain.pem + privkey.pem (Let's Encrypt ou CA interna)
docker compose -f deploy/docker-compose.prod.yml --env-file .env up -d --build
docker compose -f deploy/docker-compose.prod.yml exec web uv run python manage.py createsuperuser
```

- `web`: gunicorn + uvicorn workers, migra e coleta estáticos no boot; `/health/` para o balanceador.
- `worker`/`beat`: Celery (SLA a cada 15 min, reentrega de webhooks a cada 5 min, alertas de reposição 07:00).
- `nginx`: TLS, estáticos, `/media`, limite de upload 25 MB, `/metrics` só rede interna.
- `backup`: `pg_dump -Fc` diário, 30 dias, no volume `backups` — copie para fora do host (rsync/S3).
- Anexos: volume `media` por padrão; defina `AWS_*` no `.env` para S3/MinIO.

Restaurar: `pg_restore -h db -U postgres -d sistema_interno --clean /backups/sistema_<stamp>.dump`.
