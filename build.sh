#!/usr/bin/env bash
# Lo ejecuta Render en cada despliegue.
set -o errexit

pip install uv
uv sync --frozen --no-dev
source .venv/bin/activate

python manage.py collectstatic --no-input
python manage.py migrate --no-input
# Pone a los usuarios de prueba la clave de SIGMA_CLAVE_DEMO. Los datos ficticios solo se cargan una vez.
python manage.py datos_ejemplo
