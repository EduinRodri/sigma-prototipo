"""
Facturas PDF de ejemplo con aspecto real, para los soportes de los datos ficticios.

Se escriben a mano con operadores PDF básicos (texto, líneas y rectángulos) para no
agregar una dependencia solo por esto. Todo es ficticio y el pie lo dice: el
documento no tiene validez fiscal.
"""

from datetime import date

ANCHO, ALTO = 612, 540  # ancho carta, media hoja de alto, en puntos

CLIENTE = (
    "Frutera Las Garzas S.A.S.",
    "NIT 901.000.000-0 (ficticio)",
    "Vía 40 # 73-290, Barranquilla, Atlántico",
)

# Datos de presentación de cada proveedor de ejemplo: dirección y color de su membrete.
MEMBRETES = {
    "Taller Mecánico El Pistón": ("Cra. 38 # 45-12, Barranquilla", (0.70, 0.13, 0.13)),
    "Llantas del Caribe": ("Calle 30 # 8-55, Soledad, Atlántico", (0.11, 0.30, 0.56)),
    "Lubricentro La 30": ("Calle 30 # 21-40, Barranquilla", (0.85, 0.47, 0.07)),
    "Electroautos Rápido": ("Cra. 46 # 70-18, Barranquilla", (0.20, 0.45, 0.25)),
    "Repuestos Diésel Norte": ("Calle 11 # 15-30, Malambo, Atlántico", (0.25, 0.25, 0.30)),
}

# Anchos de Helvetica (por 1000) de los caracteres de las cifras, para alinear a la derecha.
_ANCHO_CIFRA = {**{c: 556 for c in "0123456789$"}, ".": 278, ",": 278, " ": 278, "%": 889}


def _pesos(valor):
    return f"${valor:,}".replace(",", ".")


def _escapar(texto):
    datos = texto.encode("cp1252", errors="replace")
    return datos.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


class _Lienzo:
    def __init__(self):
        self.ops = []

    def texto(self, x, y, texto, tam=9, negrita=False, color=(0.13, 0.15, 0.17)):
        fuente = b"F2" if negrita else b"F1"
        self.ops.append(
            b"BT %.3f %.3f %.3f rg /%s %.1f Tf %.1f %.1f Td (%s) Tj ET"
            % (*color, fuente, tam, x, y, _escapar(texto))
        )

    def cifra(self, x_derecha, y, texto, tam=9, negrita=False):
        """Texto numérico alineado a la derecha en x_derecha."""
        ancho = sum(_ANCHO_CIFRA.get(c, 556) for c in texto) * tam / 1000
        self.texto(x_derecha - ancho, y, texto, tam, negrita)

    def rect(self, x, y, w, h, color):
        self.ops.append(b"%.3f %.3f %.3f rg %.1f %.1f %.1f %.1f re f" % (*color, x, y, w, h))

    def linea(self, x1, y1, x2, y2, gris=0.82, grosor=0.6):
        self.ops.append(b"%.2f G %.2f w %.1f %.1f m %.1f %.1f l S" % (gris, grosor, x1, y1, x2, y2))

    def pdf(self):
        flujo = b"\n".join(self.ops)
        objetos = [
            b"<</Type/Catalog/Pages 2 0 R>>",
            b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
            b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 %d %d]/Contents 4 0 R"
            b"/Resources<</Font<</F1 5 0 R/F2 6 0 R>>>>>>" % (ANCHO, ALTO),
            b"<</Length %d>>stream\n%s\nendstream" % (len(flujo), flujo),
            b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica/Encoding/WinAnsiEncoding>>",
            b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica-Bold/Encoding/WinAnsiEncoding>>",
        ]
        salida = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        posiciones = []
        for i, obj in enumerate(objetos, start=1):
            posiciones.append(len(salida))
            salida += b"%d 0 obj\n%s\nendobj\n" % (i, obj)
        inicio_xref = len(salida)
        salida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
        for p in posiciones:
            salida += b"%010d 00000 n \n" % p
        salida += b"trailer\n<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % (len(objetos) + 1, inicio_xref)
        return bytes(salida)


def factura_pdf(proveedor, nit, placa, categoria, descripcion, monto, fecha: date, numero):
    """Factura de una página cuyo total es exactamente `monto` (IVA del 19 % incluido)."""
    direccion, color = MEMBRETES.get(proveedor, ("Barranquilla, Atlántico", (0.25, 0.25, 0.30)))
    subtotal = round(monto / 1.19)
    iva = monto - subtotal
    repuestos = int(round(subtotal * 0.7, -3))
    mano_obra = subtotal - repuestos
    c = _Lienzo()
    gris, suave = (0.42, 0.45, 0.49), (0.96, 0.97, 0.97)

    # Membrete del proveedor
    c.rect(0, ALTO - 8, ANCHO, 8, color)
    c.rect(50, ALTO - 92, 44, 44, color)
    c.texto(61, ALTO - 78, "".join([p[0] for p in proveedor.split() if p[0].isupper()][:2]), 18, True, (1, 1, 1))
    c.texto(106, ALTO - 64, proveedor, 15, True)
    c.texto(106, ALTO - 79, f"NIT {nit or 'no registrado'}  ·  Responsable de IVA", 8.5, color=gris)
    c.texto(106, ALTO - 91, direccion, 8.5, color=gris)

    # Recuadro de número y fecha
    c.rect(392, ALTO - 104, 170, 60, suave)
    c.texto(404, ALTO - 62, "FACTURA DE VENTA", 9, True, color)
    c.texto(404, ALTO - 79, f"No. FE-{numero}", 12, True)
    c.texto(404, ALTO - 95, f"Fecha: {fecha:%d/%m/%Y}", 8.5, color=gris)

    # Cliente y vehículo
    y = ALTO - 140
    c.texto(50, y, "CLIENTE", 7.5, True, gris)
    c.texto(330, y, "VEHÍCULO", 7.5, True, gris)
    for i, linea in enumerate(CLIENTE):
        c.texto(50, y - 15 - i * 12, linea, 9.5 if i == 0 else 8.5, i == 0)
    c.texto(330, y - 15, f"Placa {placa}", 9.5, True)
    c.texto(330, y - 27, f"Servicio: {categoria}", 8.5)
    c.texto(330, y - 39, "Forma de pago: contado (efectivo)", 8.5)

    # Ítems
    y = ALTO - 214
    c.rect(50, y - 6, 512, 20, suave)
    c.texto(58, y, "Descripción", 8, True, gris)
    c.cifra(400, y, "Cant.", 8, True)
    c.cifra(478, y, "Valor unit.", 8, True)
    c.cifra(554, y, "Total", 8, True)
    filas = [(descripcion, repuestos), (f"Mano de obra: {categoria.lower()}", mano_obra)]
    for texto, valor in filas:
        y -= 26
        c.texto(58, y, texto, 9)
        c.cifra(400, y, "1")
        c.cifra(478, y, _pesos(valor))
        c.cifra(554, y, _pesos(valor))
        c.linea(50, y - 9, 562, y - 9)

    # Totales
    y -= 34
    for etiqueta, valor in (("Subtotal", subtotal), ("IVA 19 %", iva)):
        c.texto(392, y, etiqueta, 9, color=gris)
        c.cifra(554, y, _pesos(valor))
        y -= 16
    c.linea(392, y + 8, 562, y + 8, gris=0.5)
    y -= 8
    c.texto(392, y, "TOTAL", 10.5, True)
    c.cifra(554, y, _pesos(monto), 10.5, True)

    # Firma y pie
    c.linea(50, 112, 230, 112, gris=0.5)
    c.texto(50, 100, "Recibido: técnico de Frutera Las Garzas", 8, color=gris)
    c.linea(50, 62, 562, 62)
    c.texto(50, 48, "Documento de ejemplo generado por SIGMA para un prototipo académico.", 7.5, color=gris)
    c.texto(50, 37, "Proveedor y cliente ficticios. Sin validez fiscal.", 7.5, color=gris)
    return c.pdf()
