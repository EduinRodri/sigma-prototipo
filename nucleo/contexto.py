"""Datos que necesitan todas las pantallas (la barra lateral)."""

from .models import Gasto
from .roles import Rol, tiene_rol


def barra_lateral(request):
    usuario = request.user
    if not usuario.is_authenticated:
        return {}
    es_direccion = tiene_rol(usuario, Rol.DIRECCION)
    grupo = usuario.groups.first()
    nombre = usuario.get_full_name() or usuario.username
    return {
        "es_direccion": es_direccion,
        "es_gestion": tiene_rol(usuario, Rol.DIRECCION, Rol.ADMINISTRATIVA),
        "rol_actual": grupo.name if grupo else "",
        "iniciales": "".join(p[0] for p in nombre.split()[:2]).upper(),
        "por_aprobar": Gasto.objects.filter(estado=Gasto.Estado.PENDIENTE).count() if es_direccion else 0,
    }
