"""
Pruebas de las reglas de negocio. Cada prueba es un caso del proceso real
contado con nombres: el técnico, la administrativa y la directora.

Se ejecutan con:  uv run python manage.py test
"""

import os

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .models import Anticipo, Camion, Categoria, Fondo, Gasto, Proveedor, RecargaFondo, ReglaDeNegocio
from .roles import Rol, SinPermiso

PDF = b"%PDF-1.4 factura de prueba"


def factura(nombre="factura.pdf", contenido=PDF):
    return SimpleUploadedFile(nombre, contenido, content_type="application/pdf")


class BaseSigma(TestCase):
    def setUp(self):
        self.directora = self._usuario("directora", Rol.DIRECCION)
        self.administrativa = self._usuario("administrativa", Rol.ADMINISTRATIVA)
        self.tecnico = self._usuario("tecnico", Rol.TECNICO)
        self.otro_tecnico = self._usuario("otro_tecnico", Rol.TECNICO)
        self.camion = Camion.objects.create(placa="TST001")
        self.categoria = Categoria.objects.create(nombre="Frenos")
        self.proveedor = Proveedor.objects.create(nombre="Taller de prueba")

    def _usuario(self, nombre, rol):
        u = User.objects.create_user(nombre, password="x")
        u.groups.add(Group.objects.get(name=rol))
        return u

    def _anticipo(self, monto=100_000):
        return Anticipo.entregar(self.administrativa, self.tecnico, monto)

    def _gasto(self, anticipo, monto, soporte=None, **extra):
        return anticipo.registrar_gasto(
            self.tecnico, self.camion, self.categoria, self.proveedor, monto, "Cambio de pastillas",
            soporte or factura(), **extra,
        )


class RolesExistenTest(TestCase):
    def test_los_tres_roles_se_crean_al_migrar(self):
        self.assertEqual(set(Group.objects.values_list("name", flat=True)), set(Rol.TODOS))


class Regla1FondoTest(BaseSigma):
    """Solo el fondo puede quedar negativo, y el sistema lo dice."""

    def test_saldo_del_fondo_se_calcula_con_los_movimientos(self):
        RecargaFondo.registrar(self.administrativa, 300_000)
        self._anticipo(100_000)
        self.assertEqual(Fondo.saldo(), 200_000)
        self.assertFalse(Fondo.en_descubierto())

    def test_entregar_mas_de_lo_que_hay_deja_el_fondo_en_descubierto(self):
        RecargaFondo.registrar(self.administrativa, 50_000)
        self._anticipo(100_000)
        self.assertEqual(Fondo.saldo(), -50_000)
        self.assertTrue(Fondo.en_descubierto())

    def test_el_sobrante_vuelve_al_fondo_al_cerrar(self):
        RecargaFondo.registrar(self.administrativa, 100_000)
        anticipo = self._anticipo(100_000)
        self._gasto(anticipo, 60_000).aprobar(self.directora)
        anticipo.cerrar(self.administrativa)
        self.assertEqual(anticipo.monto_devuelto, 40_000)
        self.assertEqual(Fondo.saldo(), 40_000)

    def test_un_gasto_nunca_supera_el_anticipo(self):
        anticipo = self._anticipo(100_000)
        with self.assertRaisesMessage(ReglaDeNegocio, "supera lo disponible"):
            self._gasto(anticipo, 100_001)

    def test_anticipo_solo_para_tecnicos(self):
        with self.assertRaises(ReglaDeNegocio):
            Anticipo.entregar(self.administrativa, self.directora, 10_000)

    def test_el_tecnico_no_entrega_anticipos(self):
        with self.assertRaises(SinPermiso):
            Anticipo.entregar(self.tecnico, self.tecnico, 10_000)


class Regla2DisponibleTest(BaseSigma):
    """Disponible = monto − aprobados − pendientes."""

    def test_lo_pendiente_ya_descuenta(self):
        anticipo = self._anticipo(100_000)
        self._gasto(anticipo, 70_000)
        self.assertEqual(anticipo.disponible(), 30_000)
        with self.assertRaises(ReglaDeNegocio):
            self._gasto(anticipo, 70_000)

    def test_lo_rechazado_vuelve_a_estar_disponible(self):
        anticipo = self._anticipo(100_000)
        self._gasto(anticipo, 70_000).rechazar(self.directora, "La factura no es legible")
        self.assertEqual(anticipo.disponible(), 100_000)

    def test_varios_anticipos_llevan_su_saldo_por_separado(self):
        a1, a2 = self._anticipo(100_000), self._anticipo(50_000)
        self._gasto(a1, 90_000)
        self.assertEqual(a1.disponible(), 10_000)
        self.assertEqual(a2.disponible(), 50_000)

    def test_solo_el_tecnico_del_anticipo_registra_gastos(self):
        anticipo = self._anticipo()
        with self.assertRaises(ReglaDeNegocio):
            anticipo.registrar_gasto(
                self.otro_tecnico, self.camion, self.categoria, self.proveedor, 1_000, "x", factura()
            )

    def test_anticipo_cerrado_no_admite_gastos(self):
        anticipo = self._anticipo()
        anticipo.cerrar(self.administrativa)
        with self.assertRaises(ReglaDeNegocio):
            self._gasto(anticipo, 1_000)

    def test_no_se_cierra_con_gastos_pendientes(self):
        anticipo = self._anticipo()
        self._gasto(anticipo, 1_000)
        with self.assertRaisesMessage(ReglaDeNegocio, "pendientes"):
            anticipo.cerrar(self.administrativa)


class Regla3AnulacionTest(BaseSigma):
    """Un gasto aprobado no se edita: se anula con motivo y se registra otro."""

    def setUp(self):
        super().setUp()
        self.anticipo = self._anticipo(100_000)
        self.gasto = self._gasto(self.anticipo, 50_000)
        self.gasto.aprobar(self.directora)

    def test_un_gasto_aprobado_no_se_edita(self):
        self.gasto.monto = 30_000
        with self.assertRaises(ReglaDeNegocio):
            self.gasto.save()

    def test_anular_devuelve_el_monto_y_deja_rastro(self):
        self.gasto.anular(self.directora, "Monto mal digitado: eran 30.000")
        self.gasto.refresh_from_db()
        self.assertEqual(self.gasto.estado, Gasto.Estado.ANULADO)
        self.assertEqual(self.gasto.anulado_por, self.directora)
        self.assertIsNotNone(self.gasto.anulado_en)
        self.assertEqual(self.anticipo.disponible(), 100_000)

    def test_el_reemplazo_queda_enlazado_al_anulado(self):
        self.gasto.anular(self.directora, "Monto mal digitado")
        nuevo = self._gasto(self.anticipo, 30_000, reemplaza=self.gasto)
        self.assertEqual(self.gasto.reemplazado_por, nuevo)
        with self.assertRaisesMessage(ReglaDeNegocio, "ya tiene un reemplazo"):
            self._gasto(self.anticipo, 1_000, reemplaza=self.gasto)

    def test_anular_exige_motivo(self):
        with self.assertRaisesMessage(ReglaDeNegocio, "motivo"):
            self.gasto.anular(self.directora, "   ")

    def test_solo_direccion_anula(self):
        with self.assertRaises(SinPermiso):
            self.gasto.anular(self.administrativa, "x")

    def test_no_se_anula_un_gasto_pendiente(self):
        pendiente = self._gasto(self.anticipo, 1_000)
        with self.assertRaises(ReglaDeNegocio):
            pendiente.anular(self.directora, "x")


class AprobacionTest(BaseSigma):
    """La aprobación deja rastro: quién, cuándo y por qué."""

    def test_aprobar_guarda_autor_y_fecha(self):
        gasto = self._gasto(self._anticipo(), 10_000).aprobar(self.directora)
        self.assertEqual(gasto.estado, Gasto.Estado.APROBADO)
        self.assertEqual(gasto.revisado_por, self.directora)
        self.assertIsNotNone(gasto.revisado_en)

    def test_rechazar_exige_motivo(self):
        gasto = self._gasto(self._anticipo(), 10_000)
        with self.assertRaises(ReglaDeNegocio):
            gasto.rechazar(self.directora, "")

    def test_solo_direccion_aprueba(self):
        gasto = self._gasto(self._anticipo(), 10_000)
        with self.assertRaises(SinPermiso):
            gasto.aprobar(self.administrativa)

    def test_nadie_aprueba_lo_que_registro(self):
        # Una persona con los dos roles no puede aprobarse a sí misma.
        self.tecnico.groups.add(Group.objects.get(name=Rol.DIRECCION))
        gasto = self._gasto(self._anticipo(), 10_000)
        with self.assertRaisesMessage(ReglaDeNegocio, "él mismo"):
            gasto.aprobar(self.tecnico)

    def test_un_gasto_se_revisa_una_sola_vez(self):
        gasto = self._gasto(self._anticipo(), 10_000).aprobar(self.directora)
        with self.assertRaises(ReglaDeNegocio):
            gasto.rechazar(self.directora, "cambié de opinión")


class SoporteTest(BaseSigma):
    def test_el_soporte_es_obligatorio(self):
        anticipo = self._anticipo()
        with self.assertRaisesMessage(ReglaDeNegocio, "obligatorio"):
            anticipo.registrar_gasto(
                self.tecnico, self.camion, self.categoria, self.proveedor, 1_000, "x", None
            )

    def test_el_tipo_se_mira_por_contenido_no_por_nombre(self):
        anticipo = self._anticipo()
        falso = factura("factura.pdf", b"MZ esto es un ejecutable")
        with self.assertRaisesMessage(ReglaDeNegocio, "PDF, JPG o PNG"):
            self._gasto(anticipo, 1_000, soporte=falso)

    def test_el_soporte_queda_guardado(self):
        gasto = self._gasto(self._anticipo(), 1_000)
        self.assertEqual(gasto.soporte.tipo_contenido, "application/pdf")
        self.assertEqual(bytes(gasto.soporte.contenido), PDF)

    def test_limite_de_tamano(self):
        grande = factura(contenido=PDF + b"0" * (2 * 1024 * 1024))
        with self.assertRaisesMessage(ReglaDeNegocio, "2 MB"):
            self._gasto(self._anticipo(), 1_000, soporte=grande)

    def test_si_falla_el_soporte_no_queda_el_gasto(self):
        anticipo = self._anticipo()
        with self.assertRaises(ReglaDeNegocio):
            self._gasto(anticipo, 1_000, soporte=factura(contenido=b"basura"))
        self.assertFalse(anticipo.gastos.exists())


class PantallasTest(BaseSigma):
    """Las pantallas respetan los roles y llevan a cabo el flujo completo."""

    def setUp(self):
        super().setUp()
        self.anticipo = self._anticipo(100_000)

    def test_sin_sesion_se_va_al_ingreso(self):
        respuesta = self.client.get("/")
        self.assertRedirects(respuesta, "/ingresar/?next=/")

    def test_cada_rol_ve_su_inicio(self):
        for usuario in (self.directora, self.administrativa, self.tecnico):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get("/").status_code, 200)

    def test_el_tecnico_no_entra_a_fondo_ni_reportes(self):
        self.client.force_login(self.tecnico)
        for url in ("/fondo/", "/reportes/", "/anticipos/nuevo/", "/gastos/pendientes/"):
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_un_tecnico_no_ve_anticipos_ajenos(self):
        self.client.force_login(self.otro_tecnico)
        self.assertEqual(self.client.get(f"/anticipos/{self.anticipo.pk}/").status_code, 404)

    def test_un_tecnico_no_ve_soportes_ajenos(self):
        gasto = self._gasto(self.anticipo, 1_000)
        self.client.force_login(self.otro_tecnico)
        self.assertEqual(self.client.get(f"/gastos/{gasto.pk}/soporte/").status_code, 403)

    def test_flujo_completo_por_pantallas(self):
        # El técnico registra el gasto con su factura.
        self.client.force_login(self.tecnico)
        datos = {
            "camion": self.camion.pk, "categoria": self.categoria.pk, "proveedor": self.proveedor.pk,
            "fecha": "2026-10-19", "monto": 40_000, "descripcion": "Pastillas", "soporte": factura(),
        }
        self.client.post(f"/anticipos/{self.anticipo.pk}/gastos/nuevo/", datos)
        gasto = self.anticipo.gastos.get()
        self.assertEqual(gasto.estado, Gasto.Estado.PENDIENTE)

        # La directora lo aprueba desde la bandeja.
        self.client.force_login(self.directora)
        self.client.post(f"/gastos/{gasto.pk}/aprobar/", {"siguiente": "pendientes"})
        gasto.refresh_from_db()
        self.assertEqual(gasto.estado, Gasto.Estado.APROBADO)

        # La administrativa cierra el anticipo y el sobrante vuelve al fondo.
        self.client.force_login(self.administrativa)
        self.client.post(f"/anticipos/{self.anticipo.pk}/cerrar/")
        self.anticipo.refresh_from_db()
        self.assertEqual(self.anticipo.monto_devuelto, 60_000)

    def test_el_error_de_regla_se_muestra_en_pantalla(self):
        self.client.force_login(self.tecnico)
        datos = {
            "camion": self.camion.pk, "categoria": self.categoria.pk, "proveedor": self.proveedor.pk,
            "fecha": "2026-10-19", "monto": 999_999, "descripcion": "x", "soporte": factura(),
        }
        respuesta = self.client.post(f"/anticipos/{self.anticipo.pk}/gastos/nuevo/", datos, follow=True)
        self.assertContains(respuesta, "supera lo disponible")
        self.assertFalse(self.anticipo.gastos.exists())

    def test_las_acciones_solo_por_post(self):
        gasto = self._gasto(self.anticipo, 1_000)
        self.client.force_login(self.directora)
        self.assertEqual(self.client.get(f"/gastos/{gasto.pk}/aprobar/").status_code, 405)

    def test_reportes_cuentan_solo_lo_aprobado(self):
        self._gasto(self.anticipo, 30_000).aprobar(self.directora)
        self._gasto(self.anticipo, 20_000)  # pendiente: no cuenta
        self.client.force_login(self.administrativa)
        respuesta = self.client.get("/reportes/?anio=" + str(Gasto.objects.first().fecha.year))
        self.assertEqual(respuesta.context["total"], 30_000)


class DatosEjemploTest(TestCase):
    def test_el_comando_carga_datos_que_cumplen_las_reglas(self):
        from django.core.management import call_command

        call_command("datos_ejemplo", stdout=open(os.devnull, "w"))
        self.assertEqual(Fondo.saldo(), 2_400_000)
        self.assertEqual(Gasto.objects.filter(estado=Gasto.Estado.ANULADO).count(), 1)
        self.assertEqual(Gasto.objects.filter(estado=Gasto.Estado.PENDIENTE).count(), 2)

    def test_volver_a_ejecutarlo_solo_cambia_las_claves(self):
        from django.core.management import call_command

        call_command("datos_ejemplo", stdout=open(os.devnull, "w"))
        gastos = Gasto.objects.count()
        os.environ["SIGMA_CLAVE_DEMO"] = "clave-nueva-de-prueba"
        try:
            call_command("datos_ejemplo", stdout=open(os.devnull, "w"))
        finally:
            del os.environ["SIGMA_CLAVE_DEMO"]
        self.assertEqual(Gasto.objects.count(), gastos)
        self.assertTrue(User.objects.get(username="direccion").check_password("clave-nueva-de-prueba"))


class Apariencia(BaseSigma):
    """Lo visual que sí es lógica: iconos por categoría, carrusel de ingreso y navegación móvil."""

    def test_cada_categoria_tiene_su_icono_y_las_demas_la_llave(self):
        from .templatetags.sigma import icono_categoria

        self.assertEqual(icono_categoria("Frenos"), "i-freno")
        self.assertEqual(icono_categoria("Lubricación"), "i-aceite")
        self.assertEqual(icono_categoria("Eléctrico"), "i-rayo")
        self.assertEqual(icono_categoria("Algo nuevo"), "i-llave")

    def test_el_ingreso_muestra_varias_fotos_en_carrusel(self):
        from .templatetags.sigma import fotos_ingreso

        self.assertGreaterEqual(len(fotos_ingreso()), 8)
        html = self.client.get("/ingresar/").content.decode()
        self.assertGreaterEqual(html.count('class="diapositiva'), 8)
        self.assertEqual(html.count(" activa\""), 1)
        # Fotos verticales para el celular y horizontales para el PC.
        self.assertGreaterEqual(html.count("solo-celular"), 3)
        self.assertGreaterEqual(html.count("solo-pc"), 5)

    def test_el_menu_movil_con_mas_solo_aparece_para_gestion(self):
        self.client.force_login(self.administrativa)
        self.assertContains(self.client.get("/"), 'class="mas-boton"')
        self.client.force_login(self.tecnico)
        self.assertNotContains(self.client.get("/"), 'class="mas-boton"')

    def test_los_avisos_traen_boton_de_cerrar(self):
        gasto = self._gasto(self._anticipo(), 20_000)
        self.client.force_login(self.directora)
        r = self.client.post(f"/gastos/{gasto.pk}/aprobar/", {"motivo": ""}, follow=True)
        self.assertContains(r, 'class="avisos"')
        self.assertContains(r, 'class="cerrar"')

    def test_el_ingreso_ofrece_usuarios_de_prueba_ver_clave_y_anuncia_el_error(self):
        r = self.client.get("/ingresar/")
        for u in ("direccion", "administrativa", "tecnico", "tecnico2"):
            self.assertContains(r, f'data-usuario="{u}"')
        self.assertContains(r, 'class="ver-clave"')
        r = self.client.post("/ingresar/", {"username": "tecnico", "password": "mala"})
        self.assertContains(r, 'role="alert"')

    def test_el_formulario_de_gasto_ofrece_la_camara(self):
        anticipo = self._anticipo()
        self.client.force_login(self.tecnico)
        r = self.client.get(f"/anticipos/{anticipo.pk}/gastos/nuevo/")
        self.assertContains(r, 'capture="environment"')
        self.assertContains(r, 'data-camara="id_soporte"')

    def test_la_app_es_instalable_sin_exponer_datos(self):
        m = self.client.get("/manifest.webmanifest")
        self.assertEqual(m.status_code, 200)
        self.assertEqual(m.json()["display"], "standalone")
        iconos = {(i["type"], i["sizes"], i["purpose"]) for i in m.json()["icons"]}
        self.assertIn(("image/png", "192x192", "any"), iconos)
        self.assertIn(("image/png", "512x512", "maskable"), iconos)
        self.assertContains(self.client.get("/ingresar/"), 'rel="apple-touch-icon"')
        sw = self.client.get("/sw.js")
        self.assertEqual(sw.status_code, 200)
        self.assertEqual(sw["Service-Worker-Allowed"], "/")
        self.assertIn("r.mode === \"navigate\"", sw.content.decode())


class AlertasInicioTest(BaseSigma):
    """El inicio le dice a cada rol lo que necesita atención, sin tocar las reglas."""

    def test_el_tecnico_ve_por_que_le_rechazaron_un_gasto(self):
        gasto = self._gasto(self._anticipo(), 20_000)
        gasto.rechazar(self.directora, "Foto borrosa")
        self.client.force_login(self.tecnico)
        self.assertContains(self.client.get("/"), "Foto borrosa")

    def test_otro_tecnico_no_ve_rechazos_ajenos(self):
        gasto = self._gasto(self._anticipo(), 20_000)
        gasto.rechazar(self.directora, "Foto borrosa")
        self.client.force_login(self.otro_tecnico)
        self.assertNotContains(self.client.get("/"), "Foto borrosa")

    def test_la_direccion_ve_los_pendientes_viejos(self):
        from datetime import timedelta

        from django.utils import timezone

        gasto = self._gasto(self._anticipo(), 20_000)
        Gasto.objects.filter(pk=gasto.pk).update(registrado_en=timezone.now() - timedelta(days=5))
        self.client.force_login(self.directora)
        self.assertContains(self.client.get("/"), "esperando aprobación")


class GuiaDeDisenoTest(BaseSigma):
    def test_la_guia_pide_sesion(self):
        self.assertRedirects(self.client.get("/guia/"), "/ingresar/?next=/guia/")

    def test_la_guia_lista_todos_los_iconos_y_colores(self):
        self.client.force_login(self.tecnico)
        r = self.client.get("/guia/")
        self.assertEqual(r.status_code, 200)
        for esperado in ("--marca-fondo", "i-freno", "i-camara", "Una acción principal por pantalla"):
            self.assertContains(r, esperado)


class CatalogosTest(BaseSigma):
    """Los catálogos son pantallas de SIGMA: gestión los mantiene y nada se borra."""

    def test_sin_sesion_se_va_al_ingreso(self):
        self.assertEqual(self.client.get("/catalogos/camiones/").status_code, 302)

    def test_el_tecnico_no_entra(self):
        self.client.force_login(self.tecnico)
        self.assertEqual(self.client.get("/catalogos/camiones/").status_code, 403)
        self.assertEqual(self.client.post("/catalogos/categorias/nuevo/", {"nombre": "X", "activo": "on"}).status_code, 403)
        self.assertFalse(Categoria.objects.filter(nombre="X").exists())

    def test_gestion_ve_los_cuatro_catalogos(self):
        for usuario in (self.administrativa, self.directora):
            self.client.force_login(usuario)
            for tipo in ("camiones", "conductores", "proveedores", "categorias"):
                self.assertEqual(self.client.get(f"/catalogos/{tipo}/").status_code, 200)

    def test_un_catalogo_que_no_existe_da_404(self):
        self.client.force_login(self.administrativa)
        self.assertEqual(self.client.get("/catalogos/gastos/").status_code, 404)

    def test_agregar_y_buscar(self):
        self.client.force_login(self.administrativa)
        self.client.post("/catalogos/proveedores/nuevo/", {"nombre": "Repuestos Norte", "nit": "900", "activo": "on"})
        self.assertTrue(Proveedor.objects.filter(nombre="Repuestos Norte", nit="900").exists())
        respuesta = self.client.get("/catalogos/proveedores/", {"q": "norte"})
        self.assertContains(respuesta, "Repuestos Norte")
        self.assertNotContains(respuesta, "Taller de prueba")

    def test_la_placa_queda_en_mayusculas_y_no_se_repite(self):
        self.client.force_login(self.administrativa)
        self.client.post("/catalogos/camiones/nuevo/", {"placa": "abc123", "tipo": "FURGON", "activo": "on"})
        self.assertTrue(Camion.objects.filter(placa="ABC123").exists())
        respuesta = self.client.post("/catalogos/camiones/nuevo/", {"placa": "ABC123", "tipo": "FURGON", "activo": "on"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Camion.objects.filter(placa="ABC123").count(), 1)

    def test_desactivar_conserva_el_registro_y_lo_saca_de_los_gastos_nuevos(self):
        self.client.force_login(self.administrativa)
        self.client.post(f"/catalogos/categorias/{self.categoria.pk}/", {"nombre": "Frenos"})
        self.categoria.refresh_from_db()
        self.assertFalse(self.categoria.activo)
        anticipo = self._anticipo()
        self.client.force_login(self.tecnico)
        self.assertNotContains(self.client.get(f"/anticipos/{anticipo.pk}/gastos/nuevo/"), ">Frenos<")

    def test_el_menu_lleva_a_catalogos_de_sigma(self):
        self.client.force_login(self.administrativa)
        self.assertContains(self.client.get("/"), 'href="/catalogos/"')
