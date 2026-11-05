"""
Modelo de datos de SIGMA y sus reglas de negocio.

El dinero se guarda en pesos enteros: el efectivo de caja no maneja centavos.

Reglas decididas para el prototipo (ver plan-actividad-4.md):
  1. Solo el FONDO puede quedar negativo. Un gasto nunca supera lo disponible
     del anticipo; entregar un anticipo sí se permite aunque el fondo no alcance,
     y en ese caso el sistema muestra la alerta de descubierto.
  2. Disponible del anticipo = monto − gastos aprobados − gastos pendientes.
  3. Un gasto aprobado no se edita: se anula con motivo y se registra otro.
"""

from pathlib import Path

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone

from .roles import Rol, exigir_rol, tiene_rol


class ReglaDeNegocio(Exception):
    """La operación viola una regla del negocio. El mensaje se le muestra al usuario."""


def _pesos(valor):
    return f"${valor:,.0f}".replace(",", ".")


def _suma(queryset, campo="monto"):
    return queryset.aggregate(total=Sum(campo))["total"] or 0


def _exigir_motivo(motivo):
    motivo = (motivo or "").strip()
    if not motivo:
        raise ReglaDeNegocio("El motivo es obligatorio.")
    return motivo


def campo_monto():
    """Pesos enteros y nunca menos de 1."""
    return models.PositiveBigIntegerField(validators=[MinValueValidator(1)])


# ─── Catálogos ──────────────────────────────────────────────────────────────


class Catalogo(models.Model):
    """Base común: un nombre único y la posibilidad de desactivarlo sin borrarlo."""

    nombre = models.CharField(max_length=100, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        abstract = True
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Conductor(Catalogo):
    class Meta(Catalogo.Meta):
        verbose_name_plural = "conductores"


class Proveedor(Catalogo):
    nit = models.CharField("NIT", max_length=20, blank=True)

    class Meta(Catalogo.Meta):
        verbose_name_plural = "proveedores"


class Categoria(Catalogo):
    class Meta(Catalogo.Meta):
        verbose_name = "categoría"


class Camion(models.Model):
    class Tipo(models.TextChoices):
        FURGON = "FURGON", "Furgón 4 t"
        SENCILLO = "SENCILLO", "Camión sencillo 8 t"

    placa = models.CharField(max_length=10, unique=True)
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.SENCILLO)
    descripcion = models.CharField("descripción", max_length=100, blank=True)
    conductor = models.ForeignKey(
        Conductor, on_delete=models.SET_NULL, null=True, blank=True, related_name="camiones"
    )
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["placa"]
        verbose_name = "camión"
        verbose_name_plural = "camiones"

    def __str__(self):
        return self.placa

    @property
    def foto(self):
        """Foto propia del vehículo (img/vehiculos/<placa>.webp) o, si no hay, la de referencia de su tipo."""
        propia = f"nucleo/img/vehiculos/{self.placa}.webp"
        if (Path(__file__).resolve().parent / "static" / propia).exists():
            return propia
        return f"nucleo/img/camion-{self.tipo.lower()}.webp"


# ─── Fondo de caja ──────────────────────────────────────────────────────────


class RecargaFondo(models.Model):
    """Entrada de efectivo al fondo de caja."""

    fecha = models.DateField(default=timezone.localdate)
    monto = campo_monto()
    descripcion = models.CharField("descripción", max_length=200, blank=True)
    registrada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    registrada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-id"]
        verbose_name = "recarga del fondo"
        verbose_name_plural = "recargas del fondo"

    def __str__(self):
        return f"Recarga {_pesos(self.monto)} ({self.fecha})"

    @classmethod
    def registrar(cls, por, monto, descripcion="", fecha=None):
        exigir_rol(por, Rol.ADMINISTRATIVA, Rol.DIRECCION)
        if monto <= 0:
            raise ReglaDeNegocio("El monto de la recarga debe ser mayor que cero.")
        return cls.objects.create(
            monto=monto, descripcion=descripcion, fecha=fecha or timezone.localdate(), registrada_por=por
        )


class Fondo:
    """
    El fondo de caja no es una tabla: su saldo se CALCULA siempre a partir de los
    movimientos, en vez de arrastrarse de mes a mes como en la hoja de cálculo.

        saldo = recargas − anticipos entregados + sobrantes devueltos al cerrar anticipos
    """

    @staticmethod
    def saldo():
        recargas = _suma(RecargaFondo.objects.all())
        entregado = _suma(Anticipo.objects.all())
        devuelto = _suma(Anticipo.objects.all(), "monto_devuelto")
        return recargas - entregado + devuelto

    @classmethod
    def en_descubierto(cls):
        return cls.saldo() < 0


# ─── Anticipos ──────────────────────────────────────────────────────────────


class Anticipo(models.Model):
    """Efectivo que se le entrega a un técnico para reparaciones, y que luego legaliza con gastos."""

    class Estado(models.TextChoices):
        ABIERTO = "ABIERTO", "Abierto"
        CERRADO = "CERRADO", "Cerrado"

    tecnico = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="anticipos")
    monto = campo_monto()
    fecha_entrega = models.DateField(default=timezone.localdate)
    descripcion = models.CharField("descripción", max_length=200, blank=True)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ABIERTO)
    entregado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    entregado_en = models.DateTimeField(auto_now_add=True)
    monto_devuelto = models.PositiveBigIntegerField(default=0)
    cerrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    cerrado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-fecha_entrega", "-id"]

    def __str__(self):
        return f"Anticipo A-{self.pk} · {self.tecnico.get_full_name() or self.tecnico.username} · {_pesos(self.monto)}"

    # Entregar ----------------------------------------------------------------

    @classmethod
    def entregar(cls, por, tecnico, monto, descripcion="", fecha=None):
        """
        Regla 1: se permite aunque el fondo no alcance. El fondo queda en negativo
        y el sistema lo señala como descubierto; no se oculta.
        """
        exigir_rol(por, Rol.ADMINISTRATIVA, Rol.DIRECCION)
        if not tiene_rol(tecnico, Rol.TECNICO):
            raise ReglaDeNegocio("Los anticipos solo se entregan a usuarios con rol Técnico.")
        if monto <= 0:
            raise ReglaDeNegocio("El monto del anticipo debe ser mayor que cero.")
        return cls.objects.create(
            tecnico=tecnico,
            monto=monto,
            descripcion=descripcion,
            fecha_entrega=fecha or timezone.localdate(),
            entregado_por=por,
        )

    # Cálculos (regla 2) --------------------------------------------------------

    def legalizado(self):
        """Lo que ya está justificado con gastos aprobados."""
        return _suma(self.gastos.filter(estado=Gasto.Estado.APROBADO))

    def comprometido(self):
        """Aprobado + pendiente: lo que ya no se puede volver a gastar."""
        return _suma(self.gastos.filter(estado__in=[Gasto.Estado.APROBADO, Gasto.Estado.PENDIENTE]))

    def pendiente(self):
        """Registrado pero sin revisar: ya descuenta, aunque todavía no está legalizado."""
        return _suma(self.gastos.filter(estado=Gasto.Estado.PENDIENTE))

    def disponible(self):
        return self.monto - self.comprometido()

    def dias_abierto(self):
        fin = timezone.localtime(self.cerrado_en).date() if self.cerrado_en else timezone.localdate()
        return (fin - self.fecha_entrega).days

    # Registrar un gasto -------------------------------------------------------

    def registrar_gasto(self, por, camion, categoria, proveedor, monto, descripcion, soporte, fecha=None, reemplaza=None):
        """
        El técnico legaliza parte del anticipo. El gasto nace PENDIENTE de aprobación
        y desde ese momento ya descuenta del disponible (regla 2).
        """
        exigir_rol(por, Rol.TECNICO)
        with transaction.atomic():
            # Se bloquea la fila del anticipo para que dos gastos registrados al mismo
            # tiempo no puedan pasarse juntos del disponible.
            anticipo = Anticipo.objects.select_for_update().get(pk=self.pk)
            if anticipo.tecnico_id != por.id:
                raise ReglaDeNegocio("Solo el técnico que recibió el anticipo puede registrarle gastos.")
            if anticipo.estado != Anticipo.Estado.ABIERTO:
                raise ReglaDeNegocio("El anticipo está cerrado: ya no admite gastos.")
            if monto <= 0:
                raise ReglaDeNegocio("El monto del gasto debe ser mayor que cero.")
            disponible = anticipo.disponible()
            if monto > disponible:
                raise ReglaDeNegocio(
                    f"El gasto ({_pesos(monto)}) supera lo disponible del anticipo ({_pesos(disponible)})."
                )
            if reemplaza is not None:
                if reemplaza.anticipo_id != anticipo.id or reemplaza.estado != Gasto.Estado.ANULADO:
                    raise ReglaDeNegocio("Solo se puede reemplazar un gasto ANULADO del mismo anticipo.")
                if hasattr(reemplaza, "reemplazado_por"):
                    raise ReglaDeNegocio("Ese gasto anulado ya tiene un reemplazo.")
            contenido, tipo = Soporte.validar(soporte)

            gasto = Gasto.objects.create(
                anticipo=anticipo,
                camion=camion,
                categoria=categoria,
                proveedor=proveedor,
                monto=monto,
                descripcion=descripcion,
                fecha=fecha or timezone.localdate(),
                registrado_por=por,
                reemplaza=reemplaza,
            )
            Soporte.objects.create(
                gasto=gasto,
                nombre_archivo=soporte.name[:200],
                tipo_contenido=tipo,
                tamano=len(contenido),
                contenido=contenido,
            )
        return gasto

    # Cerrar -------------------------------------------------------------------

    def cerrar(self, por):
        """
        El técnico ya legalizó todo lo que iba a legalizar. Lo que no se gastó vuelve
        al fondo como sobrante devuelto.
        """
        exigir_rol(por, Rol.ADMINISTRATIVA, Rol.DIRECCION)
        with transaction.atomic():
            anticipo = Anticipo.objects.select_for_update().get(pk=self.pk)
            if anticipo.estado != Anticipo.Estado.ABIERTO:
                raise ReglaDeNegocio("El anticipo ya está cerrado.")
            if anticipo.gastos.filter(estado=Gasto.Estado.PENDIENTE).exists():
                raise ReglaDeNegocio("No se puede cerrar: tiene gastos pendientes de aprobación.")
            anticipo.monto_devuelto = anticipo.monto - anticipo.legalizado()
            anticipo.estado = Anticipo.Estado.CERRADO
            anticipo.cerrado_por = por
            anticipo.cerrado_en = timezone.now()
            anticipo.save()
        self.refresh_from_db()
        return self


# ─── Gastos ─────────────────────────────────────────────────────────────────


class Gasto(models.Model):
    """Una reparación pagada con el efectivo de un anticipo."""

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        APROBADO = "APROBADO", "Aprobado"
        RECHAZADO = "RECHAZADO", "Rechazado"
        ANULADO = "ANULADO", "Anulado"

    # Campos que fijan el gasto. Cuando deja de estar PENDIENTE, no cambian nunca.
    CAMPOS_FIJOS = ("anticipo_id", "camion_id", "categoria_id", "proveedor_id", "fecha", "monto", "descripcion")

    anticipo = models.ForeignKey(Anticipo, on_delete=models.PROTECT, related_name="gastos")
    camion = models.ForeignKey(Camion, on_delete=models.PROTECT, related_name="gastos", verbose_name="camión")
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="gastos", verbose_name="categoría")
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT, related_name="gastos")
    fecha = models.DateField(default=timezone.localdate)
    monto = campo_monto()
    descripcion = models.CharField("descripción", max_length=200)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE)

    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    registrado_en = models.DateTimeField(auto_now_add=True)

    # Rastro de la aprobación o el rechazo: quién, cuándo y por qué.
    revisado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    revisado_en = models.DateTimeField(null=True, blank=True)
    motivo_revision = models.TextField("motivo", blank=True)

    # Rastro de la anulación (regla 3).
    anulado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    anulado_en = models.DateTimeField(null=True, blank=True)
    motivo_anulacion = models.TextField("motivo de la anulación", blank=True)
    reemplaza = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="reemplazado_por"
    )

    class Meta:
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"Gasto G-{self.pk} · {self.camion} · {_pesos(self.monto)} · {self.get_estado_display()}"

    def save(self, *args, **kwargs):
        """Protección de fondo: ni el panel de administración puede editar un gasto ya revisado."""
        if self.pk:
            original = Gasto.objects.get(pk=self.pk)
            if original.estado != Gasto.Estado.PENDIENTE:
                cambiados = [c for c in self.CAMPOS_FIJOS if getattr(original, c) != getattr(self, c)]
                if cambiados:
                    raise ReglaDeNegocio("Un gasto ya revisado no se edita. Si tiene un error, se anula.")
        super().save(*args, **kwargs)

    def _revisar(self, por, nuevo_estado, motivo=""):
        exigir_rol(por, Rol.DIRECCION)
        if self.estado != Gasto.Estado.PENDIENTE:
            raise ReglaDeNegocio(f"Solo se revisan gastos pendientes; este está {self.get_estado_display().lower()}.")
        if self.registrado_por_id == por.id:
            raise ReglaDeNegocio("Nadie puede aprobar ni rechazar un gasto que registró él mismo.")
        self.estado = nuevo_estado
        self.revisado_por = por
        self.revisado_en = timezone.now()
        self.motivo_revision = motivo
        self.save()
        return self

    def aprobar(self, por, observacion=""):
        return self._revisar(por, Gasto.Estado.APROBADO, (observacion or "").strip())

    def rechazar(self, por, motivo):
        """El dinero rechazado vuelve a quedar disponible en el anticipo."""
        return self._revisar(por, Gasto.Estado.RECHAZADO, _exigir_motivo(motivo))

    def anular(self, por, motivo):
        """
        Regla 3: el gasto aprobado no se borra ni se edita. Queda ANULADO con su rastro,
        su monto vuelve a estar disponible y el técnico registra el gasto correcto.
        """
        exigir_rol(por, Rol.DIRECCION)
        motivo = _exigir_motivo(motivo)
        if self.estado != Gasto.Estado.APROBADO:
            raise ReglaDeNegocio("Solo se anulan gastos aprobados. Uno pendiente se rechaza.")
        if self.anticipo.estado != Anticipo.Estado.ABIERTO:
            raise ReglaDeNegocio("El anticipo ya está cerrado: su liquidación no se puede modificar.")
        self.estado = Gasto.Estado.ANULADO
        self.anulado_por = por
        self.anulado_en = timezone.now()
        self.motivo_anulacion = motivo
        self.save()
        return self


# ─── Soportes ───────────────────────────────────────────────────────────────


class Soporte(models.Model):
    """
    La factura o la foto que justifica el gasto. Se guarda dentro de la base de datos
    porque el disco gratis del servidor se borra en cada despliegue.
    """

    # El tipo se decide por los primeros bytes del archivo, no por lo que diga el navegador.
    FIRMAS = {
        b"%PDF": "application/pdf",
        b"\x89PNG": "image/png",
        b"\xff\xd8\xff": "image/jpeg",
    }

    gasto = models.OneToOneField(Gasto, on_delete=models.CASCADE, related_name="soporte")
    nombre_archivo = models.CharField(max_length=200)
    tipo_contenido = models.CharField(max_length=50)
    tamano = models.PositiveIntegerField("tamaño (bytes)")
    contenido = models.BinaryField()

    def __str__(self):
        return self.nombre_archivo

    @classmethod
    def validar(cls, archivo):
        """Devuelve (bytes, tipo) o lanza ReglaDeNegocio."""
        if archivo is None:
            raise ReglaDeNegocio("El soporte (factura o foto) es obligatorio.")
        if archivo.size > settings.SOPORTE_TAMANO_MAXIMO:
            raise ReglaDeNegocio("El soporte no puede pasar de 2 MB.")
        contenido = archivo.read()
        tipo = next((t for firma, t in cls.FIRMAS.items() if contenido.startswith(firma)), None)
        if tipo not in settings.SOPORTE_TIPOS_PERMITIDOS:
            raise ReglaDeNegocio("El soporte debe ser un PDF, JPG o PNG.")
        return contenido, tipo
