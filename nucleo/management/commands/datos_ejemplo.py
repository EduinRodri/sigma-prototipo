"""
Carga datos de ejemplo FICTICIOS para probar el prototipo.

    uv run python manage.py datos_ejemplo

Todo pasa por los métodos de los modelos, así que los datos cumplen las mismas
reglas que si los hubiera digitado una persona. Ningún nombre, placa ni cifra
corresponde a la empresa real.

La contraseña de los usuarios de prueba sale de la variable SIGMA_CLAVE_DEMO;
si no existe, se usa la de desarrollo local que figura en app/README.md.
"""

import os
from datetime import date

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand
from django.db import transaction

from nucleo.models import Anticipo, Camion, Categoria, Conductor, Gasto, Proveedor, RecargaFondo, Soporte

from ._facturas import factura_pdf
from nucleo.roles import Rol, asegurar_grupos

CLAVE_LOCAL = "sigma-demo-2026"

USUARIOS = [
    # usuario, nombre, apellido, rol, entra al panel de catálogos
    ("direccion", "Laura", "Méndez", Rol.DIRECCION, True),
    ("administrativa", "Carolina", "Ruiz", Rol.ADMINISTRATIVA, True),
    ("tecnico", "Andrés", "Pardo", Rol.TECNICO, False),
    ("tecnico2", "Julián", "Castro", Rol.TECNICO, False),
]
CONDUCTORES = ["Mario Quintero", "Óscar Beltrán", "Felipe Arango", "Hernán Toro"]
CAMIONES = [
    ("SGM101", "FURGON", "Chevrolet NHR 2019 · Ruta Barranquilla norte", 0),
    ("SGM102", "FURGON", "Chevrolet NHR 2021 · Ruta Soledad y Malambo", 1),
    ("SGM203", "SENCILLO", "Chevrolet NKR 2018 · Ruta Puerto Colombia", 2),
    ("SGM204", "SENCILLO", "Chevrolet NHR 2020 · Ruta Sabanalarga", 3),
    ("SGM305", "SENCILLO", "Chevrolet NHR 2017 · Reserva", None),
]
# Así se reconoce un soporte generado por este comando (el PDF en blanco de la versión anterior
# o una factura de ejemplo), para rehacerlo con la versión vigente del diseño.
MARCAS_DE_EJEMPLO = (b"Factura de ejemplo - ficticia", b"Documento de ejemplo generado por SIGMA")
CATEGORIAS = ["Frenos", "Llantas", "Motor", "Eléctrico", "Suspensión", "Lubricación"]
PROVEEDORES = [
    ("Taller Mecánico El Pistón", "900111222-1"),
    ("Llantas del Caribe", "900333444-2"),
    ("Lubricentro La 30", ""),
    ("Electroautos Rápido", "900555666-3"),
    ("Repuestos Diésel Norte", "900777888-4"),
]


def _numero(placa, fecha):
    return f"{fecha:%m%d}{placa[-3:]}"


def soporte_pdf(proveedor, placa, categoria, descripcion, monto, fecha):
    """Factura ficticia con membrete, ítems e IVA, para que cada gasto tenga un soporte creíble."""
    contenido = factura_pdf(
        proveedor.nombre, proveedor.nit, placa, categoria.nombre, descripcion, monto, fecha, _numero(placa, fecha)
    )
    return SimpleUploadedFile(f"factura-{placa}-{fecha:%Y%m%d}.pdf", contenido, content_type="application/pdf")


def actualizar_presentacion():
    """Pone al día los datos de ejemplo ya cargados: descripciones de los vehículos y facturas.

    Solo toca las placas de ejemplo y los soportes generados por este comando; lo que
    haya subido una persona queda intacto.
    """
    for placa, _, desc, _ in CAMIONES:
        Camion.objects.filter(placa=placa).update(descripcion=desc)
    for soporte in Soporte.objects.select_related("gasto__camion", "gasto__categoria", "gasto__proveedor"):
        if not any(marca in bytes(soporte.contenido) for marca in MARCAS_DE_EJEMPLO):
            continue
        g = soporte.gasto
        soporte.contenido = factura_pdf(
            g.proveedor.nombre, g.proveedor.nit, g.camion.placa, g.categoria.nombre,
            g.descripcion, g.monto, g.fecha, _numero(g.camion.placa, g.fecha),
        )
        soporte.tamano = len(soporte.contenido)
        soporte.save(update_fields=["contenido", "tamano"])


class Command(BaseCommand):
    help = "Crea los usuarios de prueba con la clave vigente y, si la base está vacía, los datos ficticios."

    @transaction.atomic
    def handle(self, *args, **opciones):
        asegurar_grupos()
        clave = os.environ.get("SIGMA_CLAVE_DEMO", CLAVE_LOCAL)
        u = {}
        for usuario, nombre, apellido, rol, staff in USUARIOS:
            persona, _ = User.objects.get_or_create(username=usuario)
            persona.first_name, persona.last_name, persona.is_staff = nombre, apellido, staff
            persona.set_password(clave)
            persona.save()
            persona.groups.set([Group.objects.get(name=rol)])
            u[usuario] = persona

        # Las claves se sincronizan siempre; los movimientos solo se cargan una vez.
        if Gasto.objects.exists() or Anticipo.objects.exists():
            actualizar_presentacion()
            self.stdout.write(self.style.WARNING(
                "Ya hay movimientos: solo se actualizaron las claves y la presentación de los datos de ejemplo."
            ))
            return

        conductores = [Conductor.objects.get_or_create(nombre=n)[0] for n in CONDUCTORES]
        camiones = {}
        for placa, tipo, desc, i in CAMIONES:
            camiones[placa] = Camion.objects.get_or_create(
                placa=placa, defaults={"tipo": tipo, "descripcion": desc, "conductor": conductores[i] if i is not None else None}
            )[0]
        cat = {n: Categoria.objects.get_or_create(nombre=n)[0] for n in CATEGORIAS}
        prov = [Proveedor.objects.get_or_create(nombre=n, defaults={"nit": nit})[0] for n, nit in PROVEEDORES]

        admin, direc, tec, tec2 = u["administrativa"], u["direccion"], u["tecnico"], u["tecnico2"]

        RecargaFondo.registrar(admin, 3_000_000, "Recarga inicial del fondo", date(2026, 8, 3))
        RecargaFondo.registrar(admin, 2_000_000, "Recarga de septiembre", date(2026, 9, 1))
        RecargaFondo.registrar(admin, 1_500_000, "Recarga de octubre", date(2026, 10, 1))

        def gasto(anticipo, tecnico, placa, categoria, proveedor, monto, desc, fecha, **extra):
            return anticipo.registrar_gasto(
                tecnico, camiones[placa], cat[categoria], prov[proveedor], monto, desc,
                soporte_pdf(prov[proveedor], placa, cat[categoria], desc, monto, fecha), fecha=fecha, **extra,
            )

        # Agosto: anticipo ya liquidado y cerrado, con sobrante devuelto.
        a1 = Anticipo.entregar(admin, tec, 1_200_000, "Mantenimiento preventivo de agosto", date(2026, 8, 4))
        gasto(a1, tec, "SGM101", "Frenos", 0, 480_000, "Cambio de pastillas y discos delanteros", date(2026, 8, 6)).aprobar(direc)
        gasto(a1, tec, "SGM203", "Lubricación", 2, 320_000, "Cambio de aceite y filtros", date(2026, 8, 12)).aprobar(direc)
        gasto(a1, tec, "SGM102", "Llantas", 1, 300_000, "Dos llantas traseras", date(2026, 8, 20)).rechazar(
            direc, "La factura no corresponde a la placa SGM102"
        )
        a1.cerrar(admin)

        # Septiembre: anticipo con una anulación y su reemplazo.
        a2 = Anticipo.entregar(admin, tec2, 1_800_000, "Reparaciones de septiembre", date(2026, 9, 2))
        gasto(a2, tec2, "SGM204", "Motor", 4, 950_000, "Cambio de bomba de agua", date(2026, 9, 5)).aprobar(direc)
        errado = gasto(a2, tec2, "SGM305", "Eléctrico", 3, 450_000, "Alternador reparado", date(2026, 9, 15))
        errado.aprobar(direc)
        errado.anular(direc, "Monto mal digitado: la factura es por $405.000")
        gasto(a2, tec2, "SGM305", "Eléctrico", 3, 405_000, "Alternador reparado", date(2026, 9, 15), reemplaza=errado).aprobar(direc)

        # Octubre: anticipo abierto con gastos aprobados y pendientes.
        a3 = Anticipo.entregar(admin, tec, 1_500_000, "Reparaciones de octubre", date(2026, 10, 5))
        gasto(a3, tec, "SGM101", "Suspensión", 0, 610_000, "Amortiguadores traseros", date(2026, 10, 7)).aprobar(direc)
        gasto(a3, tec, "SGM203", "Llantas", 1, 540_000, "Llanta de repuesto y alineación", date(2026, 10, 14))
        gasto(a3, tec, "SGM102", "Lubricación", 2, 180_000, "Engrase general", date(2026, 10, 16))

        self.stdout.write(self.style.SUCCESS("Datos de ejemplo cargados."))
        self.stdout.write("Usuarios: " + ", ".join(x[0] for x in USUARIOS))
