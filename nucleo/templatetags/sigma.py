from pathlib import Path

from django import template
from django.utils import timezone
from django.utils.text import slugify
from django.utils.timesince import timesince

from ..roles import tiene_rol as _tiene_rol

register = template.Library()


@register.filter
def pesos(valor):
    """1500000 → $1.500.000 (formato colombiano)."""
    if valor is None:
        valor = 0
    signo = "-" if valor < 0 else ""
    return f"{signo}${abs(int(valor)):,}".replace(",", ".")


_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sept", "oct", "nov", "dic"]


@register.filter
def fecha(valor):
    """date(2026, 10, 5) → «5 oct 2026». Meses abreviados como en CLDR es-CO (septiembre es «sept», sin punto dentro de una fecha)."""
    if not valor:
        return ""
    return f"{valor.day} {_MESES[valor.month - 1]} {valor.year}"


@register.filter
def fechahora(valor):
    """datetime → «5 oct 2026, 2:30 p. m.» en la hora local (CLDR es-CO usa 12 horas con «a. m.» y «p. m.»)."""
    if not valor:
        return ""
    if timezone.is_aware(valor):
        valor = timezone.localtime(valor)
    sufijo = "a. m." if valor.hour < 12 else "p. m."
    return f"{fecha(valor)}, {valor.hour % 12 or 12}:{valor.minute:02d} {sufijo}"


@register.filter
def hace(fecha):
    """Antigüedad legible: «1 día, 1 hora» (Django en español omite el espacio tras la coma)."""
    return timesince(fecha).replace(",", ", ").replace(",  ", ", ")


@register.filter
def tiene_rol(usuario, rol):
    return _tiene_rol(usuario, rol)


@register.filter
def get_item(diccionario, clave):
    return diccionario.get(clave)


@register.filter
def iniciales(nombre):
    """"Carlos Pérez Díaz" → "CP"."""
    return "".join(p[0] for p in str(nombre).split()[:2]).upper()


_PERSONAS = Path(__file__).resolve().parent.parent / "static" / "nucleo" / "img" / "personas"


@register.filter
def foto_persona(nombre):
    """Ruta estática del retrato de una persona, si existe (personas/carlos-perez.webp); si no, cadena vacía."""
    archivo = f"{slugify(' '.join(str(nombre).split()[:2]))}.webp"
    return f"nucleo/img/personas/{archivo}" if (_PERSONAS / archivo).exists() else ""


_ICONOS_CATEGORIA = {
    "frenos": "i-freno", "llantas": "i-llanta", "motor": "i-motor",
    "electrico": "i-rayo", "suspension": "i-suspension", "lubricacion": "i-aceite",
}


@register.filter
def icono_categoria(categoria):
    """Símbolo de _iconos.html para una categoría de gasto; i-llave si no tiene uno propio."""
    return _ICONOS_CATEGORIA.get(slugify(str(categoria)), "i-llave")


_IMG = Path(__file__).resolve().parent.parent / "static" / "nucleo" / "img"


@register.simple_tag
def fotos_ingreso():
    """Rutas estáticas de las fotos del carrusel de ingreso: img/ingreso/*.webp, en orden alfabético."""
    return [f"nucleo/img/ingreso/{p.name}" for p in sorted((_IMG / "ingreso").glob("*.webp"))]
