"""Modelo financiero de ImprontIA. Reproducible: python3 modelo_financiero.py
Moneda: USD (precios y costos constantes en dólares, tasa en dólares). Horizonte: año 0 (inversión) + 5 años.
Cada supuesto lleva la clave bib de su fuente o la marca SUPUESTO (criterio propio, explicitado).

Versión 2 (22/10/2026), alineada con los lineamientos de la cátedra (PFI · Modelo de negocio y financiamiento 2026):
- capital de trabajo por los días de cobro a instituciones (se recupera al final del horizonte);
- amortización de la inversión inicial a efectos impositivos (lineal, 3 años);
- compensación de quebrantos en el impuesto a las ganancias (hasta 5 años, LIG t.o. 2019, art. 25);
- necesidad máxima de financiamiento (mínimo del flujo acumulado) para el plan de financiamiento.
La versión 1 (13/10) se obtiene con V1=True.
"""
import math
import numpy_financial as npf

V1 = False

FX_SUELDOS = 1408.9662      # ARS/USD, BCRA Com. A 3500, 27/02/2026 (BCRA2026TCRef)
FX_ACTUAL  = 1515.8766      # ARS/USD, BCRA Com. A 3500, 09/10/2026 (BCRA2026TCRef)
SUELDO_SSR_ARS = 2_705_000  # mediana bruta mensual Developer SSr, sysarmy 2026.1 (Sysarmy2026)
SUELDOS_ANIO = 13           # 12 + SAC (Argentina1976LCT)
CARGAS = 0.204 + 0.06       # contribuciones 20,4 % (Argentina2019Ley27541) + obra social 6 % (Argentina1989Ley23660)

def costo_anual(sueldo_ars):
    return sueldo_ars / FX_SUELDOS * SUELDOS_ANIO * (1 + CARGAS)

COSTO_SSR = costo_anual(SUELDO_SSR_ARS)

INFRA_FIJA_MES = 2*48.00 + 30.45 + 24.00   # DigitalOcean2026Droplets, DigitalOcean2026DB, LetsEncrypt
INFRA_FIJA = INFRA_FIJA_MES * 12
INFRA_VAR_EST = 0.040 * 0.215 * 12         # 40 MB/estudiante activo almacenados todo el año (SUPUESTO)
DROPLET_EXTRA_CADA = 10_000
DROPLET_EXTRA_ANUAL = 48.00 * 12

IIBB = 0.03                 # BDO2025TarifariaCABA
COMERCIAL_VAR = 0.10        # SUPUESTO
ADMIN_FIJO = 6000.0         # SUPUESTO
TRAMO1_USD = 133_514_185.74 / FX_ACTUAL     # ARCA2026EscalaPJ
TRAMO2_USD = 1_335_141_857.38 / FX_ACTUAL

def ganancias(base):
    if base <= 0: return 0.0
    if base <= TRAMO1_USD: return 0.25*base
    if base <= TRAMO2_USD: return 0.25*TRAMO1_USD + 0.30*(base-TRAMO1_USD)
    return 0.25*TRAMO1_USD + 0.30*(TRAMO2_USD-TRAMO1_USD) + 0.35*(base-TRAMO2_USD)

RF, BETA, ERP, CRP = 0.0524, 1.28, 0.0423, 0.0971   # USTreasury2026Yield, Damodaran2026WACC, ...ERPImpl, ...CRP
KE = RF + BETA*ERP + CRP

MESES_PUESTA = 2   # el MVP ya está construido: dos meses de puesta en producción (SUPUESTO)
INV_PERSONAL = 2*COSTO_SSR*MESES_PUESTA/12
INV_LEGAL = 2000.0   # SUPUESTO: SAS (Ley 27.349), contratos tipo y evaluación de impacto
INV_SEGURIDAD = 4000.0
INVERSION = INV_PERSONAL + INV_LEGAL + INV_SEGURIDAD + INFRA_FIJA*MESES_PUESTA/12

DIAS_COBRO = 30        # SUPUESTO: suscripción anual facturada al inicio y cobrada a 30 días
ANIOS_AMORT = 3        # amortización lineal de la inversión inicial a efectos impositivos
ANIOS_QUEBRANTO = 5    # LIG t.o. 2019, art. 25

ESCENARIOS = {
  "pesimista": dict(precio=3.00, cargo_fijo=1500, est_por_cliente=1000, materias=3, nuevos=[1,2,2,2,2], churn=0.15),
  "base":      dict(precio=3.50, cargo_fijo=2000, est_por_cliente=1500, materias=4, nuevos=[2,3,3,3,3], churn=0.12),
  "optimista": dict(precio=4.00, cargo_fijo=2500, est_por_cliente=2000, materias=4, nuevos=[2,3,4,4,4], churn=0.10),
}
CLIENTES_POR_SOPORTE = 6
ANIOS_RPEC = 3

RPEC_REF = True   # caso de referencia con el Régimen de Promoción de la Economía del Conocimiento

def correr(p, rpec=None, v1=None, ke=None):
    rpec = RPEC_REF if rpec is None else rpec
    v1 = V1 if v1 is None else v1
    k = KE if ke is None else ke
    filas=[]; clientes=0.0; quebrantos=[]  # lista de [anio, monto]
    ct_prev = 0.0
    for t,n in enumerate(p["nuevos"], start=1):
        base = clientes*(1-p["churn"])
        clientes = base + n
        efectivos = base + 0.5*n
        est = efectivos*p["est_por_cliente"]
        asientos = est*p["materias"]
        ingresos = p["precio"]*asientos + p["cargo_fijo"]*efectivos
        extra = math.floor(clientes/CLIENTES_POR_SOPORTE)
        personal = (2+extra)*COSTO_SSR
        if rpec and t<=ANIOS_RPEC:
            personal -= (2+extra)*(SUELDO_SSR_ARS/FX_SUELDOS*SUELDOS_ANIO)*0.204*0.70
        infra = INFRA_FIJA + INFRA_VAR_EST*est + math.floor(est/DROPLET_EXTRA_CADA)*DROPLET_EXTRA_ANUAL
        iibb = IIBB*ingresos; comercial = COMERCIAL_VAR*ingresos
        costos = personal+infra+iibb+comercial+ADMIN_FIJO
        ebitda = ingresos-costos
        amort = 0.0 if v1 else (INVERSION/ANIOS_AMORT if t<=ANIOS_AMORT else 0.0)
        ebt = ebitda-amort
        base_imp = ebt
        if not v1:
            quebrantos = [q for q in quebrantos if t-q[0] <= ANIOS_QUEBRANTO]
            if base_imp > 0:
                for q in quebrantos:
                    uso = min(q[1], base_imp); q[1] -= uso; base_imp -= uso
                quebrantos = [q for q in quebrantos if q[1] > 1e-9]
            elif base_imp < 0:
                quebrantos.append([t, -base_imp])
        imp = ganancias(base_imp)*(0.40 if (rpec and t<=ANIOS_RPEC) else 1.0)
        ct = 0.0 if v1 else ingresos*DIAS_COBRO/365
        dct = ct - ct_prev; ct_prev = ct
        recupero = ct if (not v1 and t == len(p["nuevos"])) else 0.0
        fcf = ebitda - imp - dct + recupero
        filas.append(dict(anio=t, clientes=clientes, efectivos=efectivos, estudiantes=est, asientos=asientos, ingresos=ingresos,
            personal=personal, equipo=2+extra, infra=infra, iibb=iibb, comercial=comercial, admin=ADMIN_FIJO,
            costos=costos, ebitda=ebitda, amort=amort, resultado=ebt, ganancias=imp, dct=dct, recupero_ct=recupero, flujo=fcf))
    flujos=[-INVERSION]+[f["flujo"] for f in filas]
    van = npf.npv(k, flujos); tir = npf.irr(flujos)
    # Valor residual: la cartera se extingue a la tasa de bajas; se toma el flujo operativo del año 5 (sin recupero de CT)
    if v1:
        fcf5 = flujos[-1]
    else:  # flujo operativo normalizado del año 5: impuesto pleno (sin quebrantos ni amortización) y sin movimiento de CT
        f5 = filas[-1]; fcf5 = f5["ebitda"] - ganancias(f5["ebitda"])
    vr = fcf5*(1-p["churn"])/(k+p["churn"]) if fcf5>0 else 0.0
    flujos_vr = flujos[:-1]+[flujos[-1]+vr]
    van_vr = npf.npv(k, flujos_vr); tir_vr = npf.irr(flujos_vr)
    acum=0; payback=None; acumd=0; paybackd=None; acums=[]
    for t,f in enumerate(flujos):
        prev=acum; acum+=f; acums.append(acum)
        if payback is None and t>0 and acum>=0: payback=t-1+(-prev)/f
        prevd=acumd; fd=f/(1+k)**t; acumd+=fd
        if paybackd is None and t>0 and acumd>=0: paybackd=t-1+(-prevd)/fd
    f3=filas[2]
    fijos = f3["personal"]+INFRA_FIJA+ADMIN_FIJO
    ing_cli = p["precio"]*p["est_por_cliente"]*p["materias"] + p["cargo_fijo"]
    mc = ing_cli*(1-IIBB-COMERCIAL_VAR) - INFRA_VAR_EST*p["est_por_cliente"]
    pe_cli = fijos/mc
    nec = min(acums); anio_nec = acums.index(nec)
    return dict(filas=filas, flujos=flujos, acum=acums, van=van, tir=tir, vr=vr, van_vr=van_vr, tir_vr=tir_vr,
                payback=payback, payback_desc=paybackd, pe_clientes=pe_cli, pe_estudiantes=pe_cli*p["est_por_cliente"],
                margen_contrib=mc, fijos_anio3=fijos, necesidad=nec, anio_necesidad=anio_nec)

def precio_equilibrio(p, con_vr=True, **kw):
    lo,hi=0.5,20.0
    for _ in range(60):
        m=(lo+hi)/2; q=dict(p); q["precio"]=m
        r=correr(q, **kw); v=r["van_vr"] if con_vr else r["van"]
        if v>0: hi=m
        else: lo=m
    return hi

if __name__=="__main__":
    print(f"Ke = {KE:.4%}  Inversión {INVERSION:,.0f}")
    for kk,p in ESCENARIOS.items():
        r=correr(p)
        print(f"\n== {kk} ==")
        for f in r["filas"]:
            print({a:(round(b,1) if isinstance(b,float) else b) for a,b in f.items()})
        print("flujos", [round(x) for x in r["flujos"]], "acum", [round(x) for x in r["acum"]])
        print(f"VAN {r['van']:,.0f} TIR {r['tir']} PB {r['payback']} PBD {r['payback_desc']} VR {r['vr']:,.0f} VANVR {r['van_vr']:,.0f} TIRVR {r['tir_vr']}")
        print(f"PE {r['pe_clientes']:.2f} necesidad {r['necesidad']:,.0f} (año {r['anio_necesidad']}) Peq {precio_equilibrio(p):.2f} sinVR {precio_equilibrio(p,False):.2f}")
