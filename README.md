# SIGMA — prototipo funcional (Django)

## Instalarlo en un computador

Requisitos: [Python 3.13](https://www.python.org/downloads/) y [uv](https://docs.astral.sh/uv/getting-started/installation/), los dos gratuitos.

```bash
git clone https://github.com/EduinRodri/sigma-prototipo.git
cd sigma-prototipo
uv sync
uv run python manage.py migrate
uv run python manage.py datos_ejemplo
uv run python manage.py runserver
```

Abrir http://localhost:8000.

## Usuarios de prueba (datos ficticios)

| Usuario | Rol |
|---|---|
| `direccion` | Dirección: aprueba, rechaza y anula gastos |
| `administrativa` | Administrativa: fondo de caja, anticipos y catálogos |
| `tecnico` | Técnico: registra gastos con su soporte |
| `tecnico2` | Técnico |

En local, la contraseña de todos es `sigma-demo-2026`. En el servidor publicado se define
con la variable `SIGMA_CLAVE_DEMO`.

## Pruebas

```bash
uv run python manage.py test
```

## Nota

Prototipo académico de Proyecto de Software (Corporación Universitaria Iberoamericana, 2026).
Frutera Las Garzas es una empresa ficticia y todos los datos son de prueba.
Fotos de vehículos a partir de imágenes de Jason Lawrence, Wikimedia Commons (CC BY 2.0).
