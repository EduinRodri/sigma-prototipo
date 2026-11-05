"""
Panel de administración: aquí se mantienen los catálogos y los usuarios.

Los movimientos de dinero (recargas, anticipos, gastos) se ven aquí, pero solo
en modo lectura: se crean y se revisan desde las pantallas del sistema, que son
las que aplican las reglas de negocio.
"""

from django.contrib import admin

from .models import Anticipo, Camion, Categoria, Conductor, Gasto, Proveedor, RecargaFondo

admin.site.site_header = "Frutera Las Garzas · Catálogos de SIGMA"
admin.site.site_title = "SIGMA · Frutera Las Garzas"
admin.site.index_title = "Catálogos y usuarios"


class CatalogoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activo")
    list_filter = ("activo",)
    search_fields = ("nombre",)

    def has_delete_permission(self, request, obj=None):
        # Un catálogo usado en gastos no se borra: se desactiva.
        return False


admin.site.register(Conductor, CatalogoAdmin)
admin.site.register(Categoria, CatalogoAdmin)


@admin.register(Proveedor)
class ProveedorAdmin(CatalogoAdmin):
    list_display = ("nombre", "nit", "activo")


@admin.register(Camion)
class CamionAdmin(admin.ModelAdmin):
    list_display = ("placa", "tipo", "descripcion", "conductor", "activo")
    list_filter = ("tipo", "activo")
    search_fields = ("placa", "descripcion")

    def has_delete_permission(self, request, obj=None):
        return False


class SoloLecturaAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RecargaFondo)
class RecargaFondoAdmin(SoloLecturaAdmin):
    list_display = ("fecha", "monto", "descripcion", "registrada_por")


@admin.register(Anticipo)
class AnticipoAdmin(SoloLecturaAdmin):
    list_display = ("id", "tecnico", "monto", "fecha_entrega", "estado", "monto_devuelto")
    list_filter = ("estado",)


@admin.register(Gasto)
class GastoAdmin(SoloLecturaAdmin):
    list_display = ("id", "fecha", "camion", "categoria", "monto", "estado", "registrado_por", "revisado_por")
    list_filter = ("estado", "categoria", "camion")
