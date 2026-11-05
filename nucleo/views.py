"""
Pantallas de SIGMA. Cada vista hace tres cosas: comprueba el rol, llama al modelo
(que es quien aplica las reglas) y muestra el resultado o el error.
"""

from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import AnticipoForm, GastoForm, MotivoForm, RecargaForm
from .models import Anticipo, Camion, Fondo, Gasto, RecargaFondo, ReglaDeNegocio
from .roles import Rol, SinPermiso, tiene_rol

GESTION = (Rol.DIRECCION, Rol.ADMINISTRATIVA)


def rol_requerido(*roles):
    """Deja pasar solo a usuarios con alguno de los roles; al resto, error 403."""

    def decorador(vista):
        @wraps(vista)
        @login_required
        def envoltura(request, *args, **kwargs):
            if not tiene_rol(request.user, *roles):
                raise PermissionDenied
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador


def _ejecutar(request, accion, exito):
    """Ejecuta una operación del modelo y convierte sus errores en mensajes para el usuario."""
    try:
        resultado = accion()
    except (ReglaDeNegocio, SinPermiso) as error:
        messages.error(request, str(error))
        return None
    messages.success(request, exito)
    return resultado


def _anticipos_visibles(usuario):
    """La gestión ve todos los anticipos; un técnico, solo los suyos."""
    anticipos = Anticipo.objects.select_related("tecnico")
    if tiene_rol(usuario, *GESTION):
        return anticipos
    return anticipos.filter(tecnico=usuario)


def _puede_ver_gasto(usuario, gasto):
    return tiene_rol(usuario, *GESTION) or gasto.anticipo.tecnico_id == usuario.id


# ─── Panel ──────────────────────────────────────────────────────────────────


def _alertas(usuario, abiertos, es_gestion, es_direccion):
    """Lo que pide atención hoy (solo lectura; no cambia ninguna regla): cada rol ve lo suyo."""
    ahora = timezone.now()
    alertas = []
    if not es_gestion:
        rechazados = Gasto.objects.filter(
            anticipo__tecnico=usuario, estado=Gasto.Estado.RECHAZADO, revisado_en__gte=ahora - timedelta(days=14)
        ).order_by("-revisado_en")
        for g in rechazados[:3]:
            alertas.append({"tono": "roja", "icono": "i-alerta", "texto": f"G-{g.pk} fue rechazado: {g.motivo_revision}", "url": reverse("gasto", args=[g.pk]), "accion": "Ver y registrar de nuevo"})
    if es_direccion:
        viejos = Gasto.objects.filter(estado=Gasto.Estado.PENDIENTE, registrado_en__lte=ahora - timedelta(days=3)).count()
        if viejos:
            alertas.append({"tono": "ambar", "icono": "i-reloj", "texto": f"{viejos} gasto{'s' if viejos != 1 else ''} lleva{'n' if viejos != 1 else ''} más de 3 días esperando aprobación.", "url": reverse("pendientes"), "accion": "Revisar ahora"})
    for a in abiertos:
        if a.dias_abierto() > 30:
            alertas.append({"tono": "ambar", "icono": "i-reloj", "texto": f"El anticipo A-{a.pk} lleva {a.dias_abierto()} días abierto.", "url": reverse("anticipo", args=[a.pk]), "accion": f"Ver anticipo A-{a.pk}"})
    return alertas[:4]


@login_required
def inicio(request):
    abiertos = _anticipos_visibles(request.user).filter(estado=Anticipo.Estado.ABIERTO)
    contexto = {
        "abiertos": abiertos,
        "es_gestion": tiene_rol(request.user, *GESTION),
        "es_direccion": tiene_rol(request.user, Rol.DIRECCION),
        "es_tecnico": tiene_rol(request.user, Rol.TECNICO),
    }
    recientes = Gasto.objects.select_related("camion", "categoria", "anticipo__tecnico").order_by("-registrado_en")
    if not contexto["es_gestion"]:
        recientes = recientes.filter(anticipo__tecnico=request.user)
    contexto["recientes"] = recientes[:6]
    contexto["alertas"] = _alertas(request.user, abiertos, contexto["es_gestion"], contexto["es_direccion"])
    if contexto["es_gestion"]:
        hoy = timezone.localdate()
        contexto["saldo_fondo"] = Fondo.saldo()
        contexto["pendientes"] = Gasto.objects.filter(estado=Gasto.Estado.PENDIENTE).count()
        contexto["aprobado_mes"] = Gasto.objects.filter(
            estado=Gasto.Estado.APROBADO, fecha__year=hoy.year, fecha__month=hoy.month
        ).aggregate(t=Sum("monto"))["t"] or 0
    return render(request, "nucleo/inicio.html", contexto)


# ─── Fondo de caja ──────────────────────────────────────────────────────────


@rol_requerido(*GESTION)
def fondo(request):
    form = RecargaForm(request.POST or None, initial={"fecha": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        datos = form.cleaned_data
        hecho = _ejecutar(
            request,
            lambda: RecargaFondo.registrar(request.user, datos["monto"], datos["descripcion"], datos["fecha"]),
            "Recarga registrada.",
        )
        if hecho:
            return redirect("fondo")
    return render(
        request,
        "nucleo/fondo.html",
        {"form": form, "saldo": Fondo.saldo(), "recargas": RecargaFondo.objects.select_related("registrada_por")},
    )


# ─── Anticipos ──────────────────────────────────────────────────────────────


@login_required
def anticipos(request):
    q = request.GET.get("q", "").strip()
    # Al buscar se mira en todos los estados, salvo que se elija uno.
    estado = request.GET.get("estado", "TODOS" if q else Anticipo.Estado.ABIERTO)
    visibles = _anticipos_visibles(request.user)
    if q:
        filtro = (
            Q(tecnico__first_name__icontains=q) | Q(tecnico__last_name__icontains=q)
            | Q(tecnico__username__icontains=q) | Q(descripcion__icontains=q)
            | Q(gastos__camion__placa__icontains=q)
        )
        numero = q.lstrip("#")
        if numero.isdigit():
            filtro |= Q(pk=int(numero))
        visibles = visibles.filter(filtro).distinct()
    conteos = dict(visibles.order_by().values("estado").annotate(n=Count("id", distinct=True)).values_list("estado", "n"))
    lista = visibles.filter(estado=estado) if estado in Anticipo.Estado.values else visibles
    return render(
        request,
        "nucleo/anticipos.html",
        {
            "anticipos": lista, "estado": estado, "q": q,
            "conteos": conteos, "total": sum(conteos.values()),
            "puede_entregar": tiene_rol(request.user, *GESTION),
        },
    )


@rol_requerido(*GESTION)
def anticipo_nuevo(request):
    form = AnticipoForm(request.POST or None, initial={"fecha": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        anticipo = _ejecutar(
            request,
            lambda: Anticipo.entregar(request.user, d["tecnico"], d["monto"], d["descripcion"], d["fecha"]),
            "Anticipo entregado.",
        )
        if anticipo:
            if Fondo.en_descubierto():
                messages.warning(request, "Atención: con este anticipo el fondo de caja quedó en negativo.")
            return redirect("anticipo", anticipo.pk)
    return render(request, "nucleo/anticipo_nuevo.html", {"form": form, "saldo_fondo": Fondo.saldo()})


@login_required
def anticipo(request, pk):
    anticipo = get_object_or_404(_anticipos_visibles(request.user), pk=pk)
    return render(
        request,
        "nucleo/anticipo.html",
        {
            "anticipo": anticipo,
            "gastos": anticipo.gastos.select_related("camion", "categoria", "proveedor"),
            "puede_registrar": anticipo.tecnico_id == request.user.id
            and anticipo.estado == Anticipo.Estado.ABIERTO,
            "puede_cerrar": tiene_rol(request.user, *GESTION) and anticipo.estado == Anticipo.Estado.ABIERTO,
        },
    )


@require_POST
@rol_requerido(*GESTION)
def anticipo_cerrar(request, pk):
    anticipo = get_object_or_404(Anticipo, pk=pk)
    _ejecutar(request, lambda: anticipo.cerrar(request.user), "Anticipo cerrado. El sobrante volvió al fondo.")
    return redirect("anticipo", pk)


# ─── Gastos ─────────────────────────────────────────────────────────────────


@rol_requerido(Rol.TECNICO)
def gasto_nuevo(request, pk):
    anticipo = get_object_or_404(Anticipo, pk=pk, tecnico=request.user)
    form = GastoForm(request.POST or None, request.FILES or None, anticipo=anticipo,
                     initial={"fecha": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        gasto = _ejecutar(
            request,
            lambda: anticipo.registrar_gasto(
                request.user, d["camion"], d["categoria"], d["proveedor"], d["monto"], d["descripcion"],
                d["soporte"], fecha=d["fecha"], reemplaza=d["reemplaza"],
            ),
            "Gasto registrado. Queda pendiente de aprobación.",
        )
        if gasto:
            return redirect("anticipo", pk)
    return render(request, "nucleo/gasto_nuevo.html", {"form": form, "anticipo": anticipo})


@login_required
def gasto(request, pk):
    gasto = get_object_or_404(Gasto.objects.select_related("anticipo__tecnico", "soporte"), pk=pk)
    if not _puede_ver_gasto(request.user, gasto):
        raise PermissionDenied
    es_direccion = tiene_rol(request.user, Rol.DIRECCION)
    return render(
        request,
        "nucleo/gasto.html",
        {
            "gasto": gasto,
            "form": MotivoForm(),
            "puede_revisar": es_direccion and gasto.estado == Gasto.Estado.PENDIENTE
            and gasto.registrado_por_id != request.user.id,
            "puede_anular": es_direccion and gasto.estado == Gasto.Estado.APROBADO
            and gasto.anticipo.estado == Anticipo.Estado.ABIERTO,
        },
    )


@require_POST
@rol_requerido(Rol.DIRECCION)
def gasto_revisar(request, pk, accion):
    gasto = get_object_or_404(Gasto, pk=pk)
    motivo = request.POST.get("motivo", "")
    acciones = {
        "aprobar": (lambda: gasto.aprobar(request.user, motivo), "Gasto aprobado."),
        "rechazar": (lambda: gasto.rechazar(request.user, motivo), "Gasto rechazado."),
        "anular": (lambda: gasto.anular(request.user, motivo), "Gasto anulado. Su monto volvió al anticipo."),
    }
    if accion not in acciones:
        raise PermissionDenied
    funcion, exito = acciones[accion]
    _ejecutar(request, funcion, exito)
    if request.POST.get("siguiente") == "pendientes":
        return redirect("pendientes")
    return redirect("gasto", pk)


@rol_requerido(Rol.DIRECCION)
def pendientes(request):
    lista = Gasto.objects.filter(estado=Gasto.Estado.PENDIENTE).select_related(
        "anticipo__tecnico", "camion", "categoria", "proveedor", "registrado_por"
    ).order_by("registrado_en")
    return render(request, "nucleo/pendientes.html", {"gastos": lista, "form": MotivoForm()})


@login_required
def soporte(request, pk):
    gasto = get_object_or_404(Gasto.objects.select_related("anticipo", "soporte"), pk=pk)
    if not _puede_ver_gasto(request.user, gasto):
        raise PermissionDenied
    archivo = gasto.soporte
    respuesta = HttpResponse(bytes(archivo.contenido), content_type=archivo.tipo_contenido)
    respuesta["Content-Disposition"] = f'inline; filename="{archivo.nombre_archivo}"'
    respuesta["X-Content-Type-Options"] = "nosniff"
    return respuesta


# ─── Reportes ───────────────────────────────────────────────────────────────


@rol_requerido(*GESTION)
def reportes(request):
    hoy = timezone.localdate()
    try:
        anio = int(request.GET.get("anio", hoy.year))
    except ValueError:
        anio = hoy.year
    # Solo cuentan los gastos aprobados: lo pendiente aún no es un gasto reconocido.
    aprobados = Gasto.objects.filter(estado=Gasto.Estado.APROBADO, fecha__year=anio)
    por_mes = (
        aprobados.annotate(mes=TruncMonth("fecha")).values("mes")
        .annotate(total=Sum("monto"), cantidad=Count("id")).order_by("mes")
    )
    por_camion = (
        Camion.objects.annotate(
            total=Sum("gastos__monto", filter=Q(gastos__estado=Gasto.Estado.APROBADO, gastos__fecha__year=anio)),
            cantidad=Count("gastos", filter=Q(gastos__estado=Gasto.Estado.APROBADO, gastos__fecha__year=anio)),
        )
        .filter(cantidad__gt=0)
        .order_by("-total")
    )
    total = aprobados.aggregate(t=Sum("monto"))["t"] or 0
    # El máximo de cada lista es el 100 % de las barras de la gráfica.
    por_mes, por_camion = list(por_mes), list(por_camion)
    max_mes = max((f["total"] for f in por_mes), default=0)
    max_camion = max((c.total for c in por_camion), default=0)
    anios = sorted({d.year for d in Gasto.objects.dates("fecha", "year")} | {hoy.year}, reverse=True)
    return render(
        request,
        "nucleo/reportes.html",
        {
            "anio": anio, "anios": anios, "por_mes": por_mes, "por_camion": por_camion, "total": total,
            "max_mes": max_mes, "max_camion": max_camion,
        },
    )


@rol_requerido(*GESTION)
def flota(request):
    """Lista de vehículos con su gasto del año. Solo lee: no cambia nada."""
    anio = timezone.localdate().year
    aprobados = Q(gastos__estado=Gasto.Estado.APROBADO, gastos__fecha__year=anio)
    camiones = Camion.objects.select_related("conductor").annotate(
        total=Sum("gastos__monto", filter=aprobados),
        cantidad=Count("gastos", filter=aprobados),
        pendientes=Count("gastos", filter=Q(gastos__estado=Gasto.Estado.PENDIENTE)),
        ultimo=Max("gastos__fecha", filter=~Q(gastos__estado=Gasto.Estado.ANULADO)),
    )
    conteos = dict(Camion.objects.values_list("tipo").annotate(n=Count("id")))
    tipo = request.GET.get("tipo")
    if tipo in Camion.Tipo.values:
        camiones = camiones.filter(tipo=tipo)
    else:
        tipo = "TODOS"
    camiones = list(camiones)
    return render(
        request,
        "nucleo/flota.html",
        {
            "camiones": camiones, "anio": anio, "tipo": tipo, "tipos": Camion.Tipo.choices,
            "conteos": conteos, "total_flota": sum(conteos.values()),
            "total_anio": sum(c.total or 0 for c in camiones),
            "con_pendientes": sum(1 for c in camiones if c.pendientes),
        },
    )


@rol_requerido(*GESTION)
def vehiculo(request, placa):
    """Ficha de un vehículo: datos, gasto del año por categoría e historial completo."""
    camion = get_object_or_404(Camion.objects.select_related("conductor"), placa=placa)
    anio = timezone.localdate().year
    gastos = camion.gastos.select_related("anticipo__tecnico", "categoria", "proveedor", "camion")
    aprobados = gastos.filter(estado=Gasto.Estado.APROBADO, fecha__year=anio)
    por_categoria = list(
        aprobados.values("categoria__nombre").annotate(total=Sum("monto"), cantidad=Count("id")).order_by("-total")
    )
    return render(
        request,
        "nucleo/vehiculo.html",
        {
            "camion": camion, "anio": anio, "gastos": gastos,
            "total_anio": sum(f["total"] for f in por_categoria),
            "cantidad_anio": sum(f["cantidad"] for f in por_categoria),
            "pendiente": gastos.filter(estado=Gasto.Estado.PENDIENTE).aggregate(t=Sum("monto"))["t"] or 0,
            "por_categoria": por_categoria,
            "max_categoria": max((f["total"] for f in por_categoria), default=0),
        },
    )


# ─── Aplicación instalable (PWA): públicas, sin datos de la empresa ────────────
def manifest(request):
    from django.http import JsonResponse
    from django.templatetags.static import static

    return JsonResponse({
        "name": "SIGMA · Frutera Las Garzas",
        "short_name": "SIGMA",
        "description": "Anticipos y gastos de mantenimiento de la flota.",
        "lang": "es-CO",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#f3f2ea",
        "theme_color": "#2f6b3a",
        "icons": [
            {"src": static("nucleo/img/logo-garzas.svg"), "sizes": "any", "type": "image/svg+xml", "purpose": "any"},
            {"src": static("nucleo/img/iconos/icono-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": static("nucleo/img/iconos/icono-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": static("nucleo/img/iconos/icono-maskable-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }, content_type="application/manifest+json")


def service_worker(request):
    """Guarda solo archivos estáticos y una página «sin conexión»; nunca páginas con datos de usuarios."""
    from django.template.loader import render_to_string

    respuesta = HttpResponse(render_to_string("sw.js"), content_type="text/javascript")
    respuesta["Service-Worker-Allowed"] = "/"
    respuesta["Cache-Control"] = "no-cache"
    return respuesta


# ─── Guía de diseño (el «UI kit» de SIGMA) ─────────────────────────────────────
GUIA_COLORES = [
    ("--marca-fondo", "Acción primaria (botón, fondo de cabecera móvil)"),
    ("--marca", "Acentos y enlaces; en oscuro es un verde más claro"),
    ("--marca-texto", "Texto verde sobre superficie"),
    ("--marca-claro", "Fondo suave de la marca (activo, chips)"),
    ("--aviso-barra", "Dorado: acción destacada y marcador de página activa"),
    ("--aviso-claro", "Fondo de avisos y pendientes"),
    ("--alerta", "Error, rechazo, saldo negativo"),
    ("--alerta-claro", "Fondo de errores"),
    ("--ok", "Aprobado"),
    ("--info", "Abierto / informativo"),
    ("--fondo", "Fondo de la página"),
    ("--superficie", "Tarjetas y paneles"),
    ("--borde", "Separadores"),
    ("--texto", "Texto principal"),
    ("--suave", "Texto secundario"),
    ("--tenue", "Texto de apoyo (mín. 4,5:1)"),
]


@login_required
def guia(request):
    from django.template.loader import get_template
    import re

    fuente = get_template("nucleo/_iconos.html").template.source
    iconos = [i for i in re.findall(r'id="(i-[a-z-]+)"', fuente)]
    categorias = ["Frenos", "Llantas", "Motor", "Eléctrico", "Suspensión", "Lubricación", "Otra"]
    return render(request, "nucleo/guia.html", {"colores": GUIA_COLORES, "iconos": iconos, "categorias": categorias})
