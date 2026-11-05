from django.urls import path

from . import catalogos, views

urlpatterns = [
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("sw.js", views.service_worker, name="sw"),
    path("", views.inicio, name="inicio"),
    path("fondo/", views.fondo, name="fondo"),
    path("anticipos/", views.anticipos, name="anticipos"),
    path("anticipos/nuevo/", views.anticipo_nuevo, name="anticipo_nuevo"),
    path("anticipos/<int:pk>/", views.anticipo, name="anticipo"),
    path("anticipos/<int:pk>/cerrar/", views.anticipo_cerrar, name="anticipo_cerrar"),
    path("anticipos/<int:pk>/gastos/nuevo/", views.gasto_nuevo, name="gasto_nuevo"),
    path("gastos/pendientes/", views.pendientes, name="pendientes"),
    path("gastos/<int:pk>/", views.gasto, name="gasto"),
    path("gastos/<int:pk>/soporte/", views.soporte, name="soporte"),
    path("gastos/<int:pk>/<str:accion>/", views.gasto_revisar, name="gasto_revisar"),
    path("flota/", views.flota, name="flota"),
    path("flota/<str:placa>/", views.vehiculo, name="vehiculo"),
    path("reportes/", views.reportes, name="reportes"),
    path("guia/", views.guia, name="guia"),
    path("catalogos/", catalogos.inicio, name="catalogos"),
    path("catalogos/<str:tipo>/", catalogos.lista, name="catalogo"),
    path("catalogos/<str:tipo>/nuevo/", catalogos.nuevo, name="catalogo_nuevo"),
    path("catalogos/<str:tipo>/<int:pk>/", catalogos.editar, name="catalogo_editar"),
]
