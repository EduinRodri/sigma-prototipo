"""
Formularios de las pantallas. Solo validan el formato (que haya un número, una fecha...);
las reglas de negocio las aplican los modelos.
"""

from django import forms
from django.contrib.auth.models import User

from .models import Camion, Categoria, Gasto, Proveedor
from .roles import Rol


class CampoFecha(forms.DateInput):
    """El selector de fecha del navegador solo entiende el formato AAAA-MM-DD."""

    input_type = "date"

    def __init__(self, attrs=None):
        super().__init__(attrs, format="%Y-%m-%d")


class FormularioSigma(forms.Form):
    """Base de los formularios: etiquetas sin los dos puntos que Django agrega."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)


class FormularioMonto(FormularioSigma):
    monto = forms.IntegerField(min_value=1, label="Monto (pesos)")
    descripcion = forms.CharField(label="Descripción", max_length=200, required=False)


class RecargaForm(FormularioMonto):
    fecha = forms.DateField(widget=CampoFecha())


class AnticipoForm(FormularioMonto):
    tecnico = forms.ModelChoiceField(
        queryset=User.objects.filter(groups__name=Rol.TECNICO, is_active=True).order_by("first_name"),
        label="Técnico",
        empty_label="Selecciona…",
    )
    fecha = forms.DateField(label="Fecha de entrega", widget=CampoFecha())
    field_order = ["tecnico", "monto", "fecha", "descripcion"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tecnico"].label_from_instance = lambda u: u.get_full_name() or u.username


class GastoForm(FormularioSigma):
    camion = forms.ModelChoiceField(queryset=Camion.objects.filter(activo=True), label="Camión", empty_label="Selecciona…")
    categoria = forms.ModelChoiceField(queryset=Categoria.objects.filter(activo=True), label="Categoría", empty_label="Selecciona…")
    proveedor = forms.ModelChoiceField(queryset=Proveedor.objects.filter(activo=True), empty_label="Selecciona…")
    fecha = forms.DateField(widget=CampoFecha())
    monto = forms.IntegerField(min_value=1, label="Monto (pesos)")
    descripcion = forms.CharField(label="Descripción", max_length=200)
    soporte = forms.FileField(
        label="Soporte",
        help_text="Factura en PDF, JPG o PNG, máx. 2 MB.",
        widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,application/pdf,.pdf,.jpg,.jpeg,.png"}),
    )
    reemplaza = forms.ModelChoiceField(
        queryset=Gasto.objects.none(),
        required=False,
        label="Reemplaza al gasto anulado",
        empty_label="No reemplaza a ninguno",
        help_text="Solo si este gasto corrige uno que la dirección anuló.",
    )

    def __init__(self, *args, anticipo, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo los anulados de este anticipo que todavía no tienen reemplazo.
        anulados = anticipo.gastos.filter(estado=Gasto.Estado.ANULADO, reemplazado_por__isnull=True)
        self.fields["camion"].label_from_instance = lambda c: f"{c.placa} · {c.get_tipo_display()}"
        if anulados.exists():
            self.fields["reemplaza"].queryset = anulados
        else:
            del self.fields["reemplaza"]

    def clean(self):
        datos = super().clean()
        datos.setdefault("reemplaza", None)
        return datos


class MotivoForm(FormularioSigma):
    motivo = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False)
