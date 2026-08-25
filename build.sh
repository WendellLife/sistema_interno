#!/usr/bin/env bash
# Build do Render (e de qualquer PaaS): instala, coleta estáticos e migra.
set -o errexit
pip install --upgrade pip
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate --noinput
