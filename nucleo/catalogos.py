"""
Pantallas de catálogos: camiones, conductores, proveedores y categorías.

Una sola lista y un solo formulario sirven para los cuatro: cada catálogo solo declara su
modelo, su formulario y lo que muestra. Nada se borra: un registro se desactiva, porque puede
estar usado en gastos ya registrados.
"""

from django import forms
from django.contrib import messages
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from .models import Camion, Categoria, Conductor, Proveedor
from .views import GESTION, rol_requerido


class FormularioCatalogo(forms.ModelForm):
    """Base de los formularios: etiquetas sin los dos puntos que Django agrega."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)


class CamionForm(FormularioCatalogo):
    class Meta:
        model = Camion
        fields = ["placa", "tipo", "descripcion", "conductor", "activo"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["conductor"].queryset = Conductor.objects.filter(
            Q(activo=True) | Q(pk=self.instance.conductor_id)
        )
        self.fields["conductor"].empty_label = "Sin conductor"

    def clean_placa(self):
        return self.cleaned_data["placa"].strip().upper()


class ConductorForm(FormularioCatalogo):
    class Meta:
        model = Conductor
        fields = ["nombre", "activo"]


class ProveedorForm(FormularioCatalogo):
    class Meta:
        model = Proveedor
        fields = ["nombre", "nit", "activo"]


class CategoriaForm(FormularioCatalogo):
    class Meta:
        model = Categoria
        fields = ["nombre", "activo"]


def _fila_camion(c):
    return c.placa, c.descripcion, [c.get_tipo_display(), c.conductor.nombre if c.conductor else "Sin conductor"]


def _fila_nombre(c):
    return c.nombre, "", []


def _fila_proveedor(c):
    return c.nombre, "", [c.nit or "—"]


CATALOGOS = {
    "camiones": {
        "form": CamionForm, "titulo": "Camiones", "singular": "camión", "columna": "Placa",
        "columnas": ["Tipo", "Conductor"], "fila": _fila_camion, "busca": ("placa", "descripcion"),
        "queryset": lambda: Camion.objects.select_related("conductor"), "icono": "i-camion",
    },
    "conductores": {
        "form": ConductorForm, "titulo": "Conductores", "singular": "conductor", "columna": "Nombre",
        "columnas": [], "fila": _fila_nombre, "busca": ("nombre",),
        "queryset": lambda: Conductor.objects.all(), "icono": "i-persona",
    },
    "proveedores": {
        "form": ProveedorForm, "titulo": "Proveedores", "singular": "proveedor", "columna": "Nombre",
        "columnas": ["NIT"], "fila": _fila_proveedor, "busca": ("nombre", "nit"),
        "queryset": lambda: Proveedor.objects.all(), "icono": "i-caja",
    },
    "categorias": {
        "form": CategoriaForm, "titulo": "Categorías", "singular": "categoría", "columna": "Nombre",
        "columnas": [], "fila": _fila_nombre, "busca": ("nombre",),
        "queryset": lambda: Categoria.objects.all(), "icono": "i-catalogo",
    },
}


def _catalogo(tipo):
    if tipo not in CATALOGOS:
        raise Http404
    return CATALOGOS[tipo]


@rol_requerido(*GESTION)
def inicio(request):
    return redirect("catalogo", "camiones")


@rol_requerido(*GESTION)
def lista(request, tipo):
    cat = _catalogo(tipo)
    q = request.GET.get("q", "").strip()
    registros = cat["queryset"]()
    if q:
        filtro = Q()
        for campo in cat["busca"]:
            filtro |= Q(**{f"{campo}__icontains": q})
        registros = registros.filter(filtro)
    filas = []
    for r in registros:
        titulo, ayuda, celdas = cat["fila"](r)
        filas.append({"pk": r.pk, "titulo": titulo, "ayuda": ayuda, "celdas": celdas, "activo": r.activo})
    pestanas = [
        {"tipo": clave, "titulo": c["titulo"], "total": c["queryset"]().count()} for clave, c in CATALOGOS.items()
    ]
    return render(request, "nucleo/catalogos.html", {
        "tipo": tipo, "cat": cat, "filas": filas, "q": q, "pestanas": pestanas, "columnas_total": len(cat["columnas"]) + 2,
    })


def _guardar(request, tipo, instancia=None):
    cat = _catalogo(tipo)
    form = cat["form"](request.POST or None, instance=instancia)
    if request.method == "POST" and form.is_valid():
        form.save()
        accion = "actualizado" if instancia else "agregado"
        messages.success(request, f"Registro {accion} en {cat['titulo'].lower()}.")
        return redirect("catalogo", tipo)
    return render(request, "nucleo/catalogo_form.html", {"tipo": tipo, "cat": cat, "form": form, "instancia": instancia})


@rol_requerido(*GESTION)
def nuevo(request, tipo):
    return _guardar(request, tipo)


@rol_requerido(*GESTION)
def editar(request, tipo, pk):
    cat = _catalogo(tipo)
    return _guardar(request, tipo, get_object_or_404(cat["queryset"](), pk=pk))
