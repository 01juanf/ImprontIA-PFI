"""Genera el bloque de evaluación económico-financiera del capítulo 20 (v2) y la planilla anexa."""
import numpy_financial as npf
import modelo_financiero as M

def n0(x):
    s = f"{abs(x):,.0f}".replace(",", ".")
    return ("$-$" if round(x) < 0 else "") + s
def d1(x): return f"{x:.1f}".replace(".", ",")
def d2(x): return f"{x:.2f}".replace(".", ",")
def pct(x, d=1): return ("$-$" if x < 0 else "") + f"{abs(x)*100:.{d}f}".replace(".", ",") + "\\,\\%"
def k(x): return f"{x/1000:.1f}"  # miles de USD para pgfplots (punto decimal)

E = M.ESCENARIOS
R = {e: M.correr(p) for e, p in E.items()}
RP = {e: M.correr(p, rpec=True) for e, p in E.items()}
PEQ = {e: M.precio_equilibrio(p) for e, p in E.items()}
q = dict(E["base"]); q["precio"] = 3.50; B350 = M.correr(q)
ABANDONO = npf.npv(M.KE, R["pesimista"]["flujos"][:3])
def tir(x): return pct(x) if x == x else "no existe"
def pb(x): return (d1(x) + " años") if x else "no se recupera"

def tabla_flujos(e, nombre):
    r = R[e]; f = r["filas"]
    filas = [
        ("Instituciones al cierre", ["--"] + [d1(x["clientes"]) for x in f]),
        ("Estudiantes activos", ["--"] + [n0(x["estudiantes"]) for x in f]),
        ("(+) Ingresos", ["--"] + [n0(x["ingresos"]) for x in f]),
        ("($-$) Personal (personas)", ["--"] + [f'{n0(-x["personal"])} ({x["equipo"]})' for x in f]),
        ("($-$) Infraestructura", ["--"] + [n0(-x["infra"]) for x in f]),
        ("($-$) Ingresos Brutos y comercialización", ["--"] + [n0(-(x["iibb"] + x["comercial"])) for x in f]),
        ("($-$) Administración", ["--"] + [n0(-x["admin"]) for x in f]),
        ("(=) EBITDA", ["--"] + [n0(x["ebitda"]) for x in f]),
        ("($-$) Amortización de la inversión", ["--"] + [n0(-x["amort"]) if x["amort"] else "0" for x in f]),
        ("(=) Resultado antes de impuestos", ["--"] + [n0(x["resultado"]) for x in f]),
        ("($-$) Impuesto a las Ganancias", ["--"] + [n0(-x["ganancias"]) if x["ganancias"] else "0" for x in f]),
        ("(+) Amortización (no es salida de caja)", ["--"] + [n0(x["amort"]) for x in f]),
        ("($-$) Inversión inicial", [n0(r["flujos"][0])] + ["--"] * 5),
        ("($-$) Variación del capital de trabajo", ["--"] + [n0(-x["dct"]) for x in f]),
        ("(+) Recupero del capital de trabajo", ["--"] + [n0(x["recupero_ct"]) if x["recupero_ct"] else "--" for x in f]),
        ("\\textbf{(=) Flujo de fondos libre}", ["\\textbf{" + n0(v) + "}" for v in r["flujos"]]),
        ("Flujo acumulado", [n0(v) for v in r["acum"]]),
    ]
    body = "\n".join(f"        {a} & " + " & ".join(b) + " \\\\" for a, b in filas)
    return f"""\\begin{{table}}[htbp]
    \\caption{{Flujo de fondos libre, escenario {nombre} (USD)}}
    \\label{{tab:neg_flujo_{e[:3] if e != 'base' else 'base'}}}
    \\centering
    \\scriptsize
    \\setlength{{\\tabcolsep}}{{2.5pt}}
    \\begin{{tabularx}}{{\\textwidth}}{{>{{\\raggedright\\arraybackslash}}X r r r r r r}}
        \\toprule
        \\tblhead \\textbf{{Concepto}} & \\textbf{{Año 0}} & \\textbf{{Año 1}} & \\textbf{{Año 2}} & \\textbf{{Año 3}} & \\textbf{{Año 4}} & \\textbf{{Año 5}} \\\\
        \\midrule
{body}
        \\bottomrule
    \\end{{tabularx}}
\\end{{table}}
"""

def sens_rows():
    lines = []
    for campo, vals, fmt, lab in [("precio", [2.5, 3.0, 3.5, 4.0, 4.5], lambda v: "USD " + d2(v), "Precio por asiento"),
                                  ("churn", [0.05, 0.10, 0.15, 0.20], lambda v: pct(v, 0), "Bajas anuales")]:
        for v in vals:
            row = []
            for e, p in E.items():
                qq = dict(p); qq[campo] = v; row.append(n0(M.correr(qq)["van_vr"]))
            lines.append(f"        {lab}: {fmt(v)} & " + " & ".join(row) + " \\\\")
        lines.append("        \\midrule")
    for t in [0.15, 0.25, 0.30]:
        lines.append(f"        Tasa de descuento: {pct(t,0)} & " + " & ".join(n0(M.correr(p, ke=t)["van_vr"]) for p in E.values()) + " \\\\")
    lines.append("        \\midrule")
    lines.append("        Días de cobro: 0 (cobro anticipado) & " + " & ".join(n0(cobro(p, 0)) for p in E.values()) + " \\\\")
    lines.append("        Días de cobro: 90 & " + " & ".join(n0(cobro(p, 90)) for p in E.values()) + " \\\\")
    lines.append("        \\midrule")
    lines.append("        Sin beneficios de la Ley~27.506 & " + " & ".join(n0(M.correr(p, rpec=False)["van_vr"]) for p in E.values()) + " \\\\")
    return "\n".join(lines)

def cobro(p, dias):
    old = M.DIAS_COBRO; M.DIAS_COBRO = dias
    try: return M.correr(p)["van_vr"]
    finally: M.DIAS_COBRO = old

# ---- Gráficos (pgfplots) ----
def coords(xs, ys): return " ".join(f"({x},{y})" for x, y in zip(xs, ys))
def fig_acumulado():
    series = []
    estilos = {"pesimista": "color=warnline, mark=triangle*, thick", "base": "color=accent, mark=*, thick",
               "optimista": "color=improntiaazul, mark=square*, thick"}
    for e in E:
        series.append(f"            \\addplot[{estilos[e]}] coordinates {{{coords(range(6), [k(v) for v in R[e]['acum']])}}};\n            \\addlegendentry{{{e.capitalize()}}}")
    nb = R["base"]
    return f"""\\begin{{figure}}[htbp]
    \\centering
    \\begin{{tikzpicture}}
        \\begin{{axis}}[
            width=0.85\\textwidth, height=6.6cm,
            xlabel={{Año}}, ylabel={{Flujo acumulado (miles de USD)}},
            xmin=0, xmax=5, xtick={{0,1,2,3,4,5}},
            /pgf/number format/use comma, /pgf/number format/1000 sep={{.}},
            legend style={{at={{(0.03,0.97)}}, anchor=north west, font=\\small}}, legend cell align=left,
            grid=major, grid style={{gray!25}}, label style={{font=\\small}}, tick label style={{font=\\small}},
        ]
            \\addplot[black, thin, dashed, forget plot] coordinates {{(0,0) (5,0)}};
{chr(10).join(series)}
            \\node[font=\\scriptsize, anchor=north, align=center, fill=white, inner sep=1pt] at (axis cs:{nb['anio_necesidad']},{k(nb['necesidad']-45000)}) {{necesidad máxima\\\\(base): USD~{n0(-nb['necesidad'])}}};
        \\end{{axis}}
    \\end{{tikzpicture}}
    \\caption{{Flujo de fondos acumulado por escenario. El punto más bajo de cada curva es la necesidad máxima de financiamiento; el cruce con el eje, el período de recupero. Fuente: elaboración propia con el modelo financiero (Apéndice~\\ref{{apx:modelo_financiero}}).}}
    \\label{{fig:neg_acumulado}}
\\end{{figure}}
"""

def fig_ingresos_costos():
    f = R["base"]["filas"]
    ing = coords(range(1, 6), [k(x["ingresos"]) for x in f])
    cos = coords(range(1, 6), [k(x["costos"]) for x in f])
    return f"""\\begin{{figure}}[htbp]
    \\centering
    \\begin{{tikzpicture}}
        \\begin{{axis}}[
            width=0.85\\textwidth, height=6.2cm, ybar, bar width=12pt,
            xlabel={{Año}}, ylabel={{Miles de USD}}, ymin=0,
            xtick={{1,2,3,4,5}}, enlarge x limits=0.15,
            /pgf/number format/use comma,
            legend style={{at={{(0.5,-0.22)}}, anchor=north, legend columns=2, font=\\small}}, legend cell align=left,
            grid=major, grid style={{gray!25}}, label style={{font=\\small}}, tick label style={{font=\\small}},
        ]
            \\addplot[fill=improntiaazul, draw=none] coordinates {{{ing}}};
            \\addlegendentry{{Ingresos}}
            \\addplot[fill=warnline!80, draw=none] coordinates {{{cos}}};
            \\addlegendentry{{Costos operativos (sin amortización ni impuestos)}}
        \\end{{axis}}
    \\end{{tikzpicture}}
    \\caption{{Ingresos y costos operativos del escenario base. Los ingresos superan ligeramente a los costos operativos desde el segundo año y el excedente aumenta a partir del tercero; los costos están dominados por el personal y crecen por escalones al sumar una persona cada seis instituciones. Fuente: elaboración propia con el modelo financiero.}}
    \\label{{fig:neg_ingresos_costos}}
\\end{{figure}}
"""

def fig_perfil_van():
    tasas = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    def perf(e): return coords([int(t*100) for t in tasas], [k(M.correr(E[e], ke=t)["van"]) for t in tasas])
    def perf_vr(e): return coords([int(t*100) for t in tasas], [k(M.correr(E[e], ke=t)["van_vr"]) for t in tasas])
    ke = M.KE * 100
    return f"""\\begin{{figure}}[htbp]
    \\centering
    \\begin{{tikzpicture}}
        \\begin{{axis}}[
            width=0.85\\textwidth, height=6.6cm,
            xlabel={{Tasa de descuento (\\%)}}, ylabel={{VAN (miles de USD)}},
            xmin=0, xmax=60, xtick={{0,10,20,30,40,50,60}},
            /pgf/number format/use comma, /pgf/number format/1000 sep={{.}},
            legend style={{at={{(0.97,0.97)}}, anchor=north east, font=\\small}}, legend cell align=left,
            grid=major, grid style={{gray!25}}, label style={{font=\\small}}, tick label style={{font=\\small}},
        ]
            \\addplot[black, thin, dashed, forget plot] coordinates {{(0,0) (60,0)}};
            \\addplot[color=improntiaazul, mark=square*, thick] coordinates {{{perf('optimista')}}};
            \\addlegendentry{{Optimista}}
            \\addplot[color=accent, mark=*, thick] coordinates {{{perf('base')}}};
            \\addlegendentry{{Base}}
            \\addplot[gray, thick, dotted, forget plot] coordinates {{({ke:.2f},-150) ({ke:.2f},250)}};
            \\node[font=\\scriptsize, anchor=south west] at (axis cs:{ke:.2f},150) {{tasa del proyecto: {d2(ke)}\\,\\%}};
        \\end{{axis}}
    \\end{{tikzpicture}}
    \\caption{{Perfil del VAN sin valor residual según la tasa de descuento. Donde cada curva corta el cero está su TIR; la distancia entre la TIR y la tasa del proyecto es el margen de seguridad frente a una tasa mal estimada. Fuente: elaboración propia con el modelo financiero.}}
    \\label{{fig:neg_perfil_van}}
\\end{{figure}}
"""

def fig_precio():
    precios = [2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
    def ser(e):
        out = []
        for pr in precios:
            qq = dict(E[e]); qq["precio"] = pr; out.append((pr, k(M.correr(qq)["van_vr"])))
        return " ".join(f"({a},{b})" for a, b in out)
    return f"""\\begin{{figure}}[htbp]
    \\centering
    \\begin{{tikzpicture}}
        \\begin{{axis}}[
            width=0.85\\textwidth, height=6.2cm,
            xlabel={{Precio por asiento (USD)}}, ylabel={{VAN con valor residual (miles de USD)}},
            xmin=2.5, xmax=5, xtick={{2.5,3,3.5,4,4.5,5}},
            /pgf/number format/use comma, /pgf/number format/1000 sep={{.}},
            legend style={{at={{(0.03,0.97)}}, anchor=north west, font=\\small}}, legend cell align=left,
            grid=major, grid style={{gray!25}}, label style={{font=\\small}}, tick label style={{font=\\small}},
        ]
            \\addplot[black, thin, dashed, forget plot] coordinates {{(2.5,0) (5,0)}};
            \\addplot[color=warnline, mark=triangle*, thick] coordinates {{{ser('pesimista')}}};
            \\addlegendentry{{Pesimista}}
            \\addplot[color=accent, mark=*, thick] coordinates {{{ser('base')}}};
            \\addlegendentry{{Base}}
            \\addplot[color=improntiaazul, mark=square*, thick] coordinates {{{ser('optimista')}}};
            \\addlegendentry{{Optimista}}
            \\node[font=\\scriptsize, anchor=south east] at (axis cs:{PEQ['base']:.2f},0) {{base: VAN $=0$ con USD~{d2(PEQ['base'])}}};
        \\end{{axis}}
    \\end{{tikzpicture}}
    \\caption{{Sensibilidad del VAN con valor residual al precio por asiento, con los demás parámetros de cada escenario. Fuente: elaboración propia con el modelo financiero.}}
    \\label{{fig:neg_precio}}
\\end{{figure}}
"""

V = dict(
    INV=n0(M.INVERSION), KE=pct(M.KE, 2),
    **{f"VAN_{e}": n0(R[e]["van"]) for e in E}, **{f"VANVR_{e}": n0(R[e]["van_vr"]) for e in E},
    **{f"VR_{e}": n0(R[e]["vr"]) for e in E}, **{f"TIR_{e}": tir(R[e]["tir"]) for e in E},
    **{f"TIRVR_{e}": tir(R[e]["tir_vr"]) for e in E}, **{f"PB_{e}": pb(R[e]["payback"]) for e in E},
    **{f"PBD_{e}": pb(R[e]["payback_desc"]) for e in E}, **{f"PE_{e}": d1(R[e]["pe_clientes"]) for e in E},
    **{f"CLI3_{e}": d1(R[e]["filas"][2]["clientes"]) for e in E}, **{f"PEQ_{e}": d2(PEQ[e]) for e in E},
    **{f"NEC_{e}": n0(-R[e]["necesidad"]) for e in E}, **{f"ANEC_{e}": str(R[e]["anio_necesidad"]) for e in E},
    **{f"RPEC_{e}": n0(RP[e]["van_vr"]) for e in E},
    B350=n0(B350["van_vr"]), B350SIN=n0(B350["van"]), ABANDONO=n0(ABANDONO),
    CT5_base=n0(R["base"]["filas"][-1]["recupero_ct"]),
)

if __name__ == "__main__":
    import json, sys
    out = dict(V=V,
               TAB_PES=tabla_flujos("pesimista", "pesimista"), TAB_BASE=tabla_flujos("base", "base"), TAB_OPT=tabla_flujos("optimista", "optimista"),
               SENS=sens_rows(), FIG_ACUM=fig_acumulado(), FIG_IC=fig_ingresos_costos(), FIG_PERFIL=fig_perfil_van(), FIG_PRECIO=fig_precio())
    json.dump(out, open("bloque.json", "w"), ensure_ascii=False, indent=1)
    for a, b in V.items(): print(a, "=", b)
