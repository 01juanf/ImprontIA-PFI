"""Genera el diagrama de secuencia (T25) con espaciado vertical automático, en dos partes
para que el texto se imprima a 8 pt como mínimo (revisión del 22/10/2026):
  - flujo_informacion.tex   -> fases 1 a 3 (antes y durante la rendición)
  - flujo_informacion_b.tex -> fases 4 a 6 (fin de la sesión, cierre y revisión docente)

Uso: python3 gen_flujo_informacion.py   (escribe los dos archivos en la carpeta del script)
"""
import os
import sys

X = {"E": 0.0, "N": 2.65, "A": 5.3, "P": 7.95, "B": 10.6, "D": 13.25}
LEFT, RIGHT = -1.2, 14.45

items = [
    ("phase", "1. Información previa al consentimiento (RF01, RF02)"),
    ("msg", "E", "N", r"abre \texttt{/exam/\{código\}}", "msg", 1),
    ("msg", "N", "A", r"\texttt{GET /exams/\{código\}/info}", "msg", 1),
    ("msg", "A", "B", r"lee la política vigente", "msg", 1),
    ("msg", "A", "N", r"qué se registra + señales + reglas (sin consigna)", "ret", 1),
    ("msg", "E", "N", r"identificador + consentimiento", "msg", 1),
    ("phase", "2. Inicio de la sesión (RF03, RNF04)"),
    ("msg", "N", "A", r"\texttt{POST /sessions/start}", "msg", 1),
    ("msg", "A", "B", r"\texttt{Session}: fija la versión de política", "msg", 1),
    ("msg", "A", "N", r"token de sesión, señales habilitadas, consigna", "ret", 1),
    ("phase", "3. Captura durante la sesión (RF04, RNF01, RNF07)"),
    ("loop_start", r"bucle [cada 5\,s; ante fallas de red, con \textit{backoff}]"),
    ("msg", "E", "N", r"teclado, mouse, foco, pegado", "msg", 1),
    ("note", "N", "right", 28, r"filtra por señales habilitadas; conserva solo tiempos y conteos, nunca el texto; buffer local acotado", 1.02),
    ("msg", "N", "A", r"\texttt{POST /sessions/\{id\}/events}\\ (\texttt{seq} del lote + eventos)", "msg", 2),
    ("msg", "A", "B", r"\texttt{Event} (solo inserción; un lote repetido se ignora)", "msg", 1),
    ("loop_end",),
    # Fase 4 (revisión M7, 14/10): routers/sessions.py::_run_processing hace todas las lecturas y
    # escrituras de la base; processing/ (features, pipeline, indicators, anomaly) son funciones puras.
    ("phase", "4. Fin de la sesión y procesamiento por reglas (RF06, RF07, RF09, RNF05)"),
    ("msg", "E", "N", r"Finalizar y entregar (con confirmación)", "msg", 1),
    ("msg", "N", "A", r"\texttt{POST /sessions/\{id\}/end} (idempotente; respuesta entregada)", "msg", 1),
    ("msg", "A", "B", r"lee los \texttt{Event} de la sesión", "msg", 1),
    ("msg", "A", "P", r"eventos (\texttt{compute\_all\_features})", "msg", 1),
    ("msg", "P", "A", r"métricas", "ret", 1),
    ("msg", "A", "B", r"\texttt{Metric} (sesión e ítem)", "msg", 1),
    ("msg", "A", "P", r"métricas + reglas del examen (\texttt{evaluate\_session})", "msg", 1),
    ("note", "P", "right", 23, r"funciones puras: reglas con umbral; el modelo poblacional queda pendiente hasta el cierre de la evaluación", 0.72),
    ("msg", "P", "A", r"indicadores de regla", "ret", 1),
    ("msg", "A", "B", r"\texttt{Indicator} + \texttt{IndicatorMetric}; \texttt{needs\_review}", "msg", 1),
    ("msg", "A", "N", r"entrega confirmada (\texttt{procesada})", "ret", 1),
    ("phase", "5. Cierre de la evaluación y análisis de la cohorte (RNF06, RNF08)"),
    ("msg", "D", "A", r"\texttt{POST /exams/\{id\}/cerrar} (JWT)", "msg", 1),
    ("msg", "B", "A", r"métricas continuas de todas las sesiones finalizadas", "ret", 1),
    ("msg", "A", "P", r"cohorte completa (\texttt{analizar\_cohorte})", "msg", 1),
    ("note", "P", "right", 23, r"un único Isolation Forest para toda la cohorte (si hay $\geq 20$ sesiones; nivel por percentil)", 0.62),
    ("msg", "P", "A", r"marcas del modelo", "ret", 1),
    ("msg", "A", "B", r"\texttt{Indicator} del modelo; \texttt{estado\_modelo}", "msg", 1),
    ("phase", "6. Revisión docente (RF08, RF10, RF11, RNF06)"),
    ("msg", "D", "A", r"\texttt{GET /sessions?exam\_id=...} (JWT)", "msg", 1),
    ("msg", "A", "D", r"sesiones con marca ``requiere revisión'' y estado de revisión", "ret", 1),
    ("msg", "D", "A", r"\texttt{GET /sessions/\{id\}}", "msg", 1),
    ("msg", "A", "D", r"contexto, respuesta, métricas e indicadores con su métrica de origen\\ o desvíos respecto de la cohorte", "ret", 2),
    ("note", "D", "left", 26, r"decisión humana: el sistema no emite veredicto", 0.5),
    ("msg", "D", "A", r"\texttt{POST /sessions/\{id\}/reviews} (revisada o validación adicional)", "msg", 1),
    ("msg", "A", "B", r"\texttt{Review} + \texttt{ReviewIndicator}", "msg", 1),
    ("msg", "A", "D", r"historial de revisiones (solo inserción)", "ret", 1),
]

NOTA_W, NOTA_H = 1.25, 1.2  # notas más anchas y altas: texto a \scriptsize (antes \tiny)

def generar(items):
    out = []
    y = -0.75
    loop_top = None
    first_in_phase = False
    for it in items:
        kind = it[0]
        if kind == "phase":
            y -= 0.12 if y > -1 else 0.3
            out.append(f"\\draw[accent, thin] ({LEFT},{y:.2f}) -- ({RIGHT},{y:.2f});")
            out.append(f"\\node[fase] at ({LEFT},{y:.2f}) {{{it[1]}}};")
            y -= 0.52
        elif kind == "loop_start":
            y -= 0.05
            loop_top = y
            out.append(f"\\node[bucle] at ({LEFT+0.25},{y:.2f}) {{{it[1]}}};")
            y -= 0.44
        elif kind == "loop_end":
            y -= 0.12
            out.append(f"\\draw[black!55, thin] ({LEFT+0.25},{loop_top:.2f}) rectangle ({X['B']+0.55},{y:.2f});")
            y -= 0.05
        elif kind == "msg":
            _, a, b, label, style, lines = it
            y -= 0.30 + 0.29 * lines
            out.append(f"\\draw[{style}] ({X[a]},{y:.2f}) -- node[lbl, above] {{{label}}} ({X[b]},{y:.2f});")
            y -= 0.06
        elif kind == "note":
            _, at, side, w, text, h = it
            y -= 0.12
            if side == "right":
                out.append(f"\\node[nota={w*NOTA_W:.0f}mm, anchor=north west] at ({X[at]+0.12},{y:.2f}) {{{text}}};")
            else:
                out.append(f"\\node[nota={w*NOTA_W:.0f}mm, anchor=north east] at ({X[at]-0.12},{y:.2f}) {{{text}}};")
            y -= h * NOTA_H
    return out, y - 0.25



header = r"""% Diagrama de flujo de información (secuencia) del MVP de ImprontIA (T25, rúbrica 3.2).
% Estudiante -> captura -> backend -> métricas -> indicadores -> docente, con los
% endpoints y tablas reales de TESIS/pfi/mvp al 22/10/2026 (Incremento 16: modelo al cierre)
% (routers/sessions.py::_run_processing lee y escribe la base; processing/ son funciones puras;
% routers/exams.py, models.py, dashboard/src/syncQueue.ts).
% ARCHIVO GENERADO por gen_flujo_informacion.py (misma carpeta): editar allí y regenerar con
%   python3 gen_flujo_informacion.py
% El diagrama se divide en dos partes (fases 1-3 y 4-6) para imprimir el texto a 8 pt
% como mínimo; cada parte se incluye sin escalar en su propia figura:
%   \begin{figure}[p]
%     \centering
%     \input{figures/diagramas/flujo_informacion}   % o flujo_informacion_b
%     \caption{...}\label{fig:diag_flujo}
%   \end{figure}
% IMPORTANTE: las bibliotecas TikZ se cargan UNA vez en el preámbulo de main_full.tex:
%   \usetikzlibrary{arrows.meta,positioning,fit,calc,backgrounds,shapes.multipart}
% (cargarlas dentro de un entorno figure no sirve: la carga queda local a ese grupo
% y el segundo diagrama falla con "Unknown arrow tip kind 'Stealth'").
\begin{tikzpicture}[
    font={\linespread{1}\scriptsize},
    execute at begin node={\hyphenpenalty=10000},
    actor/.style={draw=accent, fill=accentlight, rounded corners=1.5pt, text width=22mm,
                  align=center, minimum height=9mm, inner sep=2pt, font={\linespread{1}\scriptsize\bfseries}},
    vida/.style={draw=black!35, dashed},
    msg/.style={-{Stealth[length=1.6mm]}, draw=black!80, semithick},
    ret/.style={-{Stealth[length=1.6mm]}, draw=black!60, dashed},
    lbl/.style={font={\linespread{1}\scriptsize}, fill=white, inner sep=1pt, align=center},
    nota/.style={draw=black!45, fill=yellow!8, font={\linespread{1}\scriptsize}, align=left, inner sep=2pt, text width=#1},
    nota/.default=25mm,
    fase/.style={font={\linespread{1}\scriptsize\bfseries}, text=white, fill=accent, inner sep=2pt, anchor=north west},
    bucle/.style={font={\linespread{1}\scriptsize\bfseries}, draw=black!55, fill=white, anchor=north west, inner sep=1.5pt},
]
% ---- Participantes y líneas de vida ----
"""
actors = {
    "E": r"Estudiante",
    "N": r"Navegador\\ \texttt{TakeExam.tsx}\\ + \texttt{capture.ts}",
    "A": r"API FastAPI\\ \texttt{routers/}",
    "P": r"Procesamiento\\ \texttt{processing/}\\ (funciones puras)",
    "B": r"Base de datos",
    "D": r"Docente\\ (dashboard)",
}
# Parte A: fases 1 a 3; parte B: fases 4 a 6 (corte en la cuarta "phase").
fases = [i for i, it in enumerate(items) if it[0] == "phase"]
partes = {"flujo_informacion.tex": items[:fases[3]], "flujo_informacion_b.tex": items[fases[3]:]}
base = os.path.dirname(os.path.abspath(__file__))
for nombre, sub in partes.items():
    out, y_end = generar(sub)
    body = [header]
    for k, txt in actors.items():
        body.append(f"\\node[actor] at ({X[k]},0) {{{txt}}};")
    body.append(f"\\foreach \\x in {{{','.join(str(v) for v in X.values())}}} {{ \\draw[vida] (\\x,-0.55) -- (\\x,{y_end:.2f}); }}")
    body.append("% ---- Mensajes (generados; ver comentario de cabecera) ----")
    body += out
    body.append("\\end{tikzpicture}\n")
    open(os.path.join(base, nombre), "w").write("\n".join(body))
    print(nombre, "alto total (cm):", round(-y_end, 2))
