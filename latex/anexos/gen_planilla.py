"""Genera Modelo_Financiero_ImprontIA.xlsx (anexo del capítulo de negocio) a partir de modelo_financiero.py."""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
import modelo_financiero as M

AZUL = Font(color="1F4E9E"); NEG = Font(bold=True); AMAR = PatternFill("solid", fgColor="FFF2CC")
wb = Workbook(); ws = wb.active; ws.title = "Instrucciones"
for r in [["Modelo económico-financiero de ImprontIA (v2, 22/10/2026)"], [],
          ["Hojas"], ["Supuestos", "Supuestos comunes y de escenario, con su fuente (valores en azul)."],
          ["Flujo_<escenario>", "Flujo de fondos libre en USD, años 0 a 5, con VAN, TIR y flujo acumulado calculados con fórmulas."],
          ["Indicadores", "Resumen de indicadores por escenario."], [],
          ["Criterios", "USD con precios constantes; tasa CAPM con prima de riesgo país (20,36 %); impuesto a las ganancias con quebrantos (5 años) y Régimen de Economía del Conocimiento (años 1-3);"],
          ["", "amortización lineal de la inversión en 3 años; capital de trabajo = 30 días de ingresos, recuperado en el año 5."],
          ["Reproducir", "python3 modelo_financiero.py ; python3 gen_planilla.py (requiere numpy-financial y openpyxl)."]]:
    ws.append(r)
ws["A1"].font = Font(bold=True, size=13); ws.column_dimensions["A"].width = 22; ws.column_dimensions["B"].width = 120

s = wb.create_sheet("Supuestos"); s.append(["Supuesto", "Valor", "Unidad", "Fuente"]); [setattr(c, "font", NEG) for c in s[1]]
filas = [
    ("Costo laboral anual por persona (SSr)", round(M.COSTO_SSR, 2), "USD/año", "Sysarmy 2026.1; LCT; Ley 27.541; Ley 23.660; BCRA"),
    ("Infraestructura fija", round(M.INFRA_FIJA, 2), "USD/año", "DigitalOcean (2026)"),
    ("Infraestructura variable", round(M.INFRA_VAR_EST, 4), "USD/estudiante-año", "DigitalOcean (2026); supuesto propio de volumen"),
    ("Ingresos Brutos", M.IIBB, "% ingresos", "BDO (2025), CABA"),
    ("Comercialización", M.COMERCIAL_VAR, "% ingresos", "Supuesto propio"),
    ("Administración", M.ADMIN_FIJO, "USD/año", "Supuesto propio"),
    ("Inversión inicial (año 0)", round(M.INVERSION, 2), "USD", "Supuesto propio (4 meses de 2 fundadores, legal, auditoría, infraestructura)"),
    ("Amortización de la inversión", M.ANIOS_AMORT, "años", "Guía de la cátedra"),
    ("Días de cobro (capital de trabajo)", M.DIAS_COBRO, "días", "Supuesto propio (30-60 días en venta a organizaciones)"),
    ("Compensación de quebrantos", M.ANIOS_QUEBRANTO, "años", "LIG t.o. 2019, art. 25"),
    ("Tasa libre de riesgo", M.RF, "", "US Treasury, 9/10/2026"),
    ("Beta software", M.BETA, "", "Damodaran (2026)"),
    ("Prima de riesgo de mercado", M.ERP, "", "Damodaran (2026)"),
    ("Prima de riesgo país Argentina", M.CRP, "", "Damodaran (2026)"),
    ("Tasa de descuento (Ke = WACC)", round(M.KE, 6), "", "CAPM + riesgo país"),
]
for f in filas:
    s.append(list(f)); s.cell(s.max_row, 2).font = AZUL
s.append([]); s.append(["Escenario", "Precio/asiento", "Cargo fijo", "Estudiantes/inst.", "Materias", "Altas años 1-5", "Bajas anuales"])
[setattr(c, "font", NEG) for c in s[s.max_row]]
for e, p in M.ESCENARIOS.items():
    s.append([e, p["precio"], p["cargo_fijo"], p["est_por_cliente"], p["materias"], "-".join(map(str, p["nuevos"])), p["churn"]])
    for c in range(2, 8): s.cell(s.max_row, c).font = AZUL; s.cell(s.max_row, c).fill = AMAR
for col, w in zip("ABCDEFG", [42, 16, 16, 18, 10, 16, 60]): s.column_dimensions[col].width = w
TASA = "Supuestos!$B$16"

ind = wb.create_sheet("Indicadores"); ind.append(["Indicador", "Pesimista", "Base", "Optimista"]); [setattr(c, "font", NEG) for c in ind[1]]
refs = {}
for e, p in M.ESCENARIOS.items():
    r = M.correr(p); w = wb.create_sheet(f"Flujo_{e}")
    w.append(["Concepto (USD)", "Año 0", "Año 1", "Año 2", "Año 3", "Año 4", "Año 5"]); [setattr(c, "font", NEG) for c in w[1]]
    F = r["filas"]
    def fila(nombre, vals): w.append([nombre] + vals)
    fila("Instituciones al cierre", [None] + [round(x["clientes"], 2) for x in F])
    fila("Estudiantes activos", [None] + [round(x["estudiantes"], 1) for x in F])
    fila("Ingresos", [None] + [round(x["ingresos"], 2) for x in F])
    fila("Personal", [None] + [-round(x["personal"], 2) for x in F])
    fila("Infraestructura", [None] + [-round(x["infra"], 2) for x in F])
    fila("Ingresos Brutos y comercialización", [None] + [-round(x["iibb"] + x["comercial"], 2) for x in F])
    fila("Administración", [None] + [-x["admin"] for x in F])
    w.append(["EBITDA", None] + [f"=SUM({c}4:{c}8)" for c in "CDEFG"])
    fila("Amortización", [None] + [-round(x["amort"], 2) for x in F])
    w.append(["Resultado antes de impuestos", None] + [f"={c}9+{c}10" for c in "CDEFG"])
    fila("Impuesto a las ganancias (con quebrantos)", [None] + [-round(x["ganancias"], 2) for x in F])
    w.append(["+ Amortización", None] + [f"=-{c}10" for c in "CDEFG"])
    fila("Inversión inicial", [-round(M.INVERSION, 2)] + [None] * 5)
    fila("Variación del capital de trabajo", [None] + [-round(x["dct"], 2) for x in F])
    fila("Recupero del capital de trabajo", [None] + [round(x["recupero_ct"], 2) for x in F])
    w.append(["Flujo de fondos libre", "=B14"] + [f"={c}11+{c}12+{c}13+{c}15+{c}16" for c in "CDEFG"])
    w.append(["Flujo acumulado", "=B17"] + [f"={p}18+{c}17" for p, c in zip("BCDEF", "CDEFG")])
    w.append([]); w.append(["VAN sin valor residual", f"=NPV({TASA},C17:G17)+B17"])
    w.append(["TIR sin valor residual", "=IRR(B17:G17)"])
    w.append(["Valor residual al año 5 (del modelo)", round(r["vr"], 2)])
    w.append(["VAN con valor residual", f"=B20+B22/(1+{TASA})^5"])
    w.append(["Necesidad máxima de financiamiento", "=-MIN(B18:G18)"])
    for row in w.iter_rows(min_row=2, min_col=2):
        for c in row: c.number_format = '#,##0;[Red]-#,##0'
    w["B21"].number_format = "0.0%"; w.column_dimensions["A"].width = 42
    refs[e] = f"Flujo_{e}"
for nombre, celda in [("VAN sin valor residual", "B20"), ("TIR sin valor residual", "B21"), ("VAN con valor residual", "B23"), ("Necesidad máxima de financiamiento", "B24")]:
    ind.append([nombre] + [f"={refs[e]}!{celda}" for e in M.ESCENARIOS])
ind.column_dimensions["A"].width = 40
wb._sheets.insert(2, wb._sheets.pop(wb.sheetnames.index("Indicadores")))
wb.save("Modelo_Financiero_ImprontIA.xlsx"); print("ok")
