"""
Los tres roles del proceso y lo que cada uno puede hacer.

Cada rol es un grupo de Django. Un usuario puede pertenecer a uno o varios.
Las reglas de negocio (aprobar, entregar anticipos...) preguntan por el rol;
los permisos de Django solo controlan qué ve cada uno en el panel de administración.
"""

from django.contrib.auth.models import Group, Permission


class Rol:
    DIRECCION = "Dirección"
    ADMINISTRATIVA = "Administrativa"
    TECNICO = "Técnico"

    TODOS = (DIRECCION, ADMINISTRATIVA, TECNICO)


class SinPermiso(Exception):
    """El usuario no tiene el rol que exige la operación."""


def tiene_rol(usuario, *roles):
    if not usuario or not usuario.is_authenticated:
        return False
    return usuario.groups.filter(name__in=roles).exists()


def exigir_rol(usuario, *roles):
    if not tiene_rol(usuario, *roles):
        raise SinPermiso(f"Esta operación es solo para: {', '.join(roles)}.")


# Permisos del panel de administración por rol.
_CATALOGOS = ("camion", "conductor", "proveedor", "categoria")
_PERMISOS_ADMIN = {
    Rol.DIRECCION: [f"{accion}_{m}" for m in _CATALOGOS for accion in ("add", "change", "view")]
    + ["view_recargafondo", "view_anticipo", "view_gasto"],
    Rol.ADMINISTRATIVA: [f"{accion}_{m}" for m in _CATALOGOS for accion in ("add", "change", "view")]
    + ["view_recargafondo", "view_anticipo", "view_gasto"],
    Rol.TECNICO: [],
}


def asegurar_grupos(**kwargs):
    """Crea los tres grupos con sus permisos. Se puede ejecutar muchas veces."""
    for nombre, codigos in _PERMISOS_ADMIN.items():
        grupo, _ = Group.objects.get_or_create(name=nombre)
        permisos = Permission.objects.filter(content_type__app_label="nucleo", codename__in=codigos)
        grupo.permissions.set(permisos)
