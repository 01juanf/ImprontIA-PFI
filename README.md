# ImprontIA-PFI

Proyecto Final de Ingeniería (UADE, 2026) — **ImprontIA: Trazabilidad de autoría en evaluaciones digitales**

Autores: Hackbartt, M.J. — Ferreira, J.I.

## Para el evaluador

- **Informe final:** [`PFI_Hackbartt_Ferreira.pdf`](PFI_Hackbartt_Ferreira.pdf) (fuente en `latex/`).
- **Plataforma en línea:** https://improntia-dashboard.vercel.app — cuenta docente de demostración `docente@improntia.com`, clave `demo`. Los estudiantes ingresan con el código de la evaluación en https://improntia-dashboard.vercel.app/rendir.
- **Versión evaluada:** etiqueta `v1.0`.
- **Dataset sintético y generador:** `mvp/docs/evaluacion/` y `mvp/backend/app/evaluation/synthetic.py`.
- **Reproducir los resultados:** preparar el entorno como indica el Apéndice F del informe y, desde `mvp/`, correr
  `bash scripts/reproducir.sh --python backend/.venv/bin/python` (unos 15 minutos; detalle en `mvp/README.md`).
- **Planilla del modelo económico-financiero:** `latex/anexos/Modelo_Financiero_ImprontIA.xlsx` (Apéndice G).

## Contenido del repositorio

```
ImprontIA-PFI/
├── PFI_Hackbartt_Ferreira.pdf   Versión compilada más reciente del documento
├── latex/                       Fuente LaTeX completa (main_full.tex)
│   ├── chapters/                Capítulos y apéndices
│   ├── figures/                 Figuras (PNG) y diagramas en TikZ (figures/diagramas/*.tex)
│   ├── tables/, config/, images/
│   └── biblio.bib               Bibliografía (biblatex + biber)
└── mvp/                         Implementación del MVP (ver mvp/README.md)
    ├── backend/                 API FastAPI + procesamiento (reglas + Isolation Forest) + evaluación
    ├── dashboard/               Frontend React + TypeScript: vista del estudiante (con la
    │                            captura de señales embebida) y panel docente
    ├── scripts/                 Capturas de la demo, prueba interna end-to-end y prueba de
    │                            resiliencia ante cortes de red (Playwright)
    └── docs/                    Bitácora, evaluación, guía de despliegue y protocolo de simulaciones
```

La captura de señales ocurre **dentro de la propia plataforma web**, no mediante
una extensión de navegador (ver `mvp/docs/bitacora.md`, Incremento 2b).

## Cómo compilar el documento

Requiere una distribución TeX con `pdflatex` y `biber` (TeX Live o MacTeX).

```bash
cd latex
pdflatex main_full.tex
biber main_full
pdflatex main_full.tex
pdflatex main_full.tex
```

El PDF resultante es `latex/main_full.pdf`. Los diagramas funcionales
(componentes, flujo de información, clases) están en TikZ y se compilan con el
documento; el de secuencia se regenera con
`python3 latex/figures/diagramas/gen_flujo_informacion.py latex/figures/diagramas/flujo_informacion.tex`.

## Cómo correr el MVP

Resumen (detalle en [`mvp/README.md`](mvp/README.md)):

```bash
# Backend (Python 3.11 o 3.12)
cd mvp/backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m scripts.seed_teacher docente@uade.edu.ar 1234
uvicorn app.main:app --port 8010

# Dashboard (otra terminal)
cd mvp/dashboard
npm install
npm run dev        # http://localhost:5173
```

## Pruebas y evaluación

| Qué | Comando (desde `mvp/`) | Resultado |
|---|---|---|
| Tests automatizados del backend (unitarios + integración de la API) | `cd backend && pytest` | 142 pruebas aprobadas sobre SQLite y 1 omitida, que solo corre sobre PostgreSQL (`TEST_DATABASE_URL`) |
| Tests unitarios del dashboard | `cd dashboard && npm test` | 36 pruebas |
| Build del dashboard (tipado TypeScript + bundle) | `cd dashboard && npm run build` | — |
| Evaluación con datos sintéticos (FAR, FRR, AUC-ROC, EER) | `cd backend && python -m scripts.evaluar` | `docs/evaluacion/resultados_sinteticos.md` |
| Prueba interna end-to-end (4 escenarios en navegador) | `python scripts/prueba_interna.py --backend-python backend/.venv/bin/python` | `docs/evaluacion/prueba_interna.md` |
| Resiliencia ante cortes de red (3 escenarios en navegador) | `python scripts/prueba_red.py --backend-python backend/.venv/bin/python` | `docs/evaluacion/prueba_red.md` |
| Verificación de un despliegue por HTTP | `python scripts/verificar_despliegue.py --help` | ver `docs/despliegue.md` |
| Exportación y análisis de simulaciones etiquetadas | `cd backend && python -m scripts.exportar_sesiones` / `python -m scripts.analizar_reales` | ver `docs/simulaciones/protocolo.md` |
| Capturas de pantalla de la demo | `python scripts/capturas_demo.py --backend-python backend/.venv/bin/python` | `docs/capturas/*.png` |

La evaluación usa **datos sintéticos** y la prueba interna, escenarios
guionados: validan el procedimiento y el funcionamiento del sistema, no su
desempeño con estudiantes reales (el piloto con voluntarios queda como trabajo
futuro). La prueba se puede repetir a mano con
`mvp/docs/evaluacion/protocolo_prueba_manual.md`.

## Historial

El registro técnico del MVP, incremento por incremento, está en
`mvp/docs/bitacora.md`.
