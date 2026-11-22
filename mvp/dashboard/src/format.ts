// Formato de presentación compartido por las vistas del dashboard (Incremento 7).

/**
 * Fecha y hora en formato local de 24 h.
 *
 * El backend devuelve ISO 8601 con offset UTC explícito (+00:00). Si llegara un
 * timestamp sin zona (API vieja), se lo trata como UTC en vez de dejar que el
 * navegador lo interprete como hora local, que corría todas las horas -3 h en
 * Argentina. `hourCycle: "h23"` evita el reloj de 12 h sin "a. m./p. m." que
 * produce `toLocaleString("es-AR")` en algunos navegadores.
 */
export function formatDateTime(iso: string): string {
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(iso);
  const d = new Date(hasZone ? iso : `${iso}Z`);
  return d.toLocaleString("es-AR", { dateStyle: "short", timeStyle: "medium", hourCycle: "h23" });
}

/** Nombres legibles de los tipos de indicador (backend: app/processing/indicators.py). */
export const INDICATOR_LABELS: Record<string, string> = {
  paste_volume_alto: "Volumen de texto pegado alto",
  cambios_pestana_frecuentes: "Cambios de pestaña frecuentes",
  perdida_foco_prolongada: "Pérdida de foco prolongada",
  ritmo_tecleo_atipico: "Ritmo de tecleo atípico",
  // Incremento 12 (R3): reencuadre del indicador del Isolation Forest. Solo cambia el texto;
  // el cálculo es el mismo. Atipicidad estadística no es conducta indebida.
  atipico_modelo_poblacional: "Proceso de interacción distinto al de la cohorte",
  captura_incompleta: "Captura incompleta (aviso informativo)",
};

/** Aclaración que acompaña siempre al indicador del modelo (Incremento 12, R3). */
export const MODEL_INDICATOR_NOTE = "Indica dónde mirar, no una conducta indebida.";

/**
 * Las variables que acompañan la marca del modelo son las de mayor desviación (z-score)
 * respecto de la cohorte: describen en qué se diferencia la sesión, pero no explican la
 * decisión del Isolation Forest (Incremento 16).
 */
export const MODEL_FEATURES_NOTE =
  "Variables con mayor desviación respecto de la cohorte (dato descriptivo: muestran en qué se diferencia la sesión, no explican por qué el modelo la marcó):";

/** Estado del análisis poblacional de una sesión (Incremento 16). */
export const MODEL_STATE_LABELS: Record<string, string> = {
  pendiente: "pendiente (se calcula al cerrar la evaluación)",
  no_evaluada: "no evaluada (la cohorte tenía menos de 20 sesiones o la sesión terminó después del cierre)",
  sin_marca: "evaluada, sin marca",
  con_marca: "evaluada, con marca",
};

export const MODEL_STATE_SHORT: Record<string, string> = {
  pendiente: "Pendiente",
  no_evaluada: "No evaluada",
  sin_marca: "Sin marca",
  con_marca: "Con marca",
};

/**
 * Qué pregunta docente responde cada parte del panorama y qué acción puede motivar
 * (Incremento 16). Son guías de lectura: el panorama describe el proceso registrado y no
 * permite inferir dificultad, atención ni aprendizaje.
 */
export const PANORAMA_GUIDE = {
  metricas:
    "¿El tiempo y la forma de trabajo fueron los esperados? Si la duración real se acerca al límite o el período sin interacción registrada es alto en muchas sesiones, conviene revisar la extensión de la consigna o el tiempo asignado.",
  indicadores:
    "¿Qué conductas registradas se repiten en la cohorte? Si muchas sesiones pegan texto o salen de la pestaña, conviene revisar si las reglas del examen las permiten y comunicarlas mejor, antes que revisar sesión por sesión.",
  modelo:
    "¿Qué sesiones conviene mirar primero? La marca del modelo ordena la revisión; las variables listadas son descriptivas y no explican la decisión del modelo.",
};

/** Indicadores que contextualizan la evidencia pero no priorizan la sesión (backend: INFORMATIVE_KINDS). */
export const INFORMATIVE_INDICATORS = ["captura_incompleta"];

export function indicatorLabel(kind: string): string {
  return INDICATOR_LABELS[kind] ?? kind.replaceAll("_", " ");
}

/** Estado de la revisión docente (derivado de la última revisión, RF11/HU08). */
export const REVIEW_STATUS_LABELS: Record<string, string> = {
  sin_revision: "Sin revisar",
  revisada: "Revisada",
  validacion_pendiente: "Validación adicional pendiente",
};

export const REVIEW_ACTION_LABELS: Record<string, string> = {
  marked_reviewed: "Marcada como revisada",
  additional_validation: "Pidió validación adicional",
};

/** Categorías de señal que se pueden habilitar por evaluación (RF04). Ver capture.ts. */
export const SIGNAL_OPTIONS = [
  { value: "keyboard", label: "Teclado (dinámica de tecleo)" },
  { value: "mouse", label: "Mouse (movimiento y clicks)" },
  { value: "scroll", label: "Scroll" },
  { value: "visibility", label: "Cambios de pestaña / foco" },
  { value: "clipboard", label: "Portapapeles (copiar / pegar)" },
];

export function signalLabel(value: string): string {
  return SIGNAL_OPTIONS.find((o) => o.value === value)?.label ?? value;
}

/**
 * Qué registra exactamente cada categoría, en palabras del estudiante (RF01, RNF02).
 * Se muestra antes del consentimiento a partir de `allowed_signals`, que es la misma
 * lista que limita la captura en capture.ts: lo informado y lo capturado no pueden
 * divergir aunque el texto libre del docente sea impreciso (Incremento 10).
 */
export const SIGNAL_STUDENT_DESCRIPTIONS: Record<string, string> = {
  keyboard:
    "Teclado: el momento en que se presiona y se suelta cada tecla. No se registra qué tecla es ni el texto que escribís.",
  mouse: "Mouse: posición del puntero (como máximo una muestra cada 100 ms) y clics.",
  scroll: "Scroll: posición de desplazamiento de la página (como máximo una muestra cada 100 ms).",
  visibility: "Pestaña y foco: cuándo la pestaña del examen deja de estar visible o pierde el foco, y cuándo vuelve.",
  clipboard:
    "Portapapeles: cuándo copiás, cortás o pegás. De lo que pegás solo se registra la cantidad de caracteres: " +
    "el texto se lee un instante en tu navegador para contarlo y no se guarda ni se envía.",
};

/**
 * Reglas del examen que cambian la relevancia de algunos eventos (Incremento 12, R2).
 * Si están permitidos, el indicador se conserva con nivel bajo y no marca la sesión
 * para revisión. Backend: app/processing/rules.py.
 */
export const RULE_OPTIONS = [
  { value: "permite_pegado", label: "Se permite pegar texto (p. ej. material propio o citas)" },
  { value: "permite_otras_pestanas", label: "Se permite consultar otras pestañas o ventanas" },
] as const;

export type RuleFlag = (typeof RULE_OPTIONS)[number]["value"];

/** Métricas del panorama de la evaluación (Incremento 12, R1). Backend: app/processing/panorama.py. */
export const PANORAMA_METRIC_LABELS: Record<string, string> = {
  session_wall_duration_ms: "Duración de la sesión (inicio a entrega)",
  session_duration_ms: "Período con eventos registrados",
  idle_ratio: "Proporción sin interacción registrada",
  paste_chars_total: "Caracteres pegados",
  tab_switch_count: "Veces que la pestaña quedó oculta",
  focus_loss_duration_total_ms: "Tiempo con la pestaña oculta",
};

/** Valor de una métrica del panorama en unidades legibles. */
export function formatPanoramaValue(metric: string, value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (metric.endsWith("_ms")) {
    const s = value / 1000;
    if (s < 59.5) return `${s.toFixed(s < 10 ? 1 : 0).replace(".", ",")} s`;
    const total = Math.round(s); // se redondea antes de separar: evita "1 min 60 s"
    const m = Math.floor(total / 60);
    return `${m} min ${total - m * 60} s`;
  }
  if (metric === "idle_ratio") return formatPercent(value);
  return Number.isInteger(value) ? String(value) : value.toFixed(1).replace(".", ",");
}

/** Proporción 0–1 como porcentaje entero ("25 %"). */
export function formatPercent(share: number): string {
  return `${Math.round(share * 100)} %`;
}

/** Ancho de una barra CSS (0–100 %) relativo al máximo; sin librerías de gráficos. */
export function barWidth(value: number, max: number): string {
  if (!(max > 0) || !(value > 0)) return "0%";
  return `${Math.min(100, (value / max) * 100).toFixed(1)}%`;
}

// ---- Kit de simulación (Fase 2, P03; mvp/docs/simulaciones/protocolo.md) ----

/** Condiciones simuladas; mismos valores que `app/simulacion.py::CONDICIONES` del backend. */
export const SIMULATION_CONDITIONS: { value: string; label: string }[] = [
  { value: "normal", label: "Normal (rendir de verdad, sin ayuda)" },
  { value: "pegado", label: "Pegado (copiar y pegar parte de la respuesta)" },
  { value: "transcripcion", label: "Transcripción (tipear una respuesta preparada)" },
  { value: "consulta_externa", label: "Consulta externa (buscar en otra pestaña o con una IA)" },
  { value: "suplantacion", label: "Suplantación (rendir con el código de la otra persona)" },
];

/** El selector de condición aparece solo con `?simulacion=1` en el enlace del examen. */
export function isSimulationMode(search: string): boolean {
  const v = new URLSearchParams(search).get("simulacion");
  return v === "1" || v === "true";
}

/** Condición a enviar: solo en modo simulación y solo si es una de las conocidas. */
export function simulationConditionToSend(simulation: boolean, value: string): string | undefined {
  if (!simulation) return undefined;
  return SIMULATION_CONDITIONS.some((c) => c.value === value) ? value : undefined;
}

// ---- Evaluación de usabilidad (octubre 2026) ----

/** Tipo de sesión en palabras (el backend guarda "exam"). */
export const SESSION_TYPE_LABELS: Record<string, string> = {
  exam: "Examen",
  practice: "Práctica",
  simulacion: "Simulación",
};

export function sessionTypeLabel(value: string): string {
  return SESSION_TYPE_LABELS[value] ?? value;
}

/** Nombres legibles de las métricas por sesión (backend: app/processing/features.py). */
export const METRIC_LABELS: Record<string, string> = {
  keydown_count: "Teclas presionadas",
  mean_dwell_time_ms: "Duración media de pulsación (ms)",
  std_dwell_time_ms: "Variabilidad de pulsación (ms)",
  mean_flight_time_ms: "Tiempo medio entre teclas (ms)",
  mean_mouse_speed_px_ms: "Velocidad media del mouse (px/ms)",
  std_mouse_speed_px_ms: "Variabilidad de velocidad del mouse",
  click_count: "Clics",
  tab_switch_count: "Veces que la pestaña quedó oculta",
  focus_loss_duration_total_ms: "Tiempo con la pestaña oculta (ms)",
  paste_event_count: "Eventos de pegado",
  paste_chars_total: "Caracteres pegados (total)",
  copy_cut_count: "Eventos de copiar/cortar",
  idle_ratio: "Proporción del período sin interacción registrada (pausas > 2 s)",
  session_duration_ms: "Período con eventos registrados (ms)",
  capture_dropped_events: "Eventos descartados por buffer lleno",
  sync_failure_count: "Interrupciones prolongadas de la sincronización",
};

/** Nombre de la métrica sin la unidad entre paréntesis ("Caracteres pegados"). */
export function metricName(metric: string): string {
  const label = METRIC_LABELS[metric] ?? PANORAMA_METRIC_LABELS[metric];
  return label ? label.replace(/\s*\((total|ms|px\/ms)\)$/, "") : metric.replaceAll("_", " ");
}

/** Valor de una métrica con su unidad, para la evidencia de un indicador ("264", "3,5 s", "25 %"). */
export function formatMetricValue(metric: string, value: unknown): string {
  if (typeof value !== "number" || Number.isNaN(value)) return value === null || value === undefined ? "—" : String(value);
  return formatPanoramaValue(metric, value);
}

/**
 * Orden de la tabla de sesiones: primero las que requieren revisión, y dentro de cada grupo
 * las más recientes primero (estable ante empates). No modifica el arreglo recibido.
 */
export function sortSessionsForReview<T extends { needs_review: boolean; started_at: string }>(sessions: T[]): T[] {
  return sessions
    .map((s, i) => ({ s, i }))
    .sort((a, b) => {
      if (a.s.needs_review !== b.s.needs_review) return a.s.needs_review ? -1 : 1;
      const ta = Date.parse(a.s.started_at);
      const tb = Date.parse(b.s.started_at);
      if (!Number.isNaN(ta) && !Number.isNaN(tb) && ta !== tb) return tb - ta;
      return a.i - b.i;
    })
    .map(({ s }) => s);
}

/**
 * Destino seguro después del login (`/login?next=...`): solo rutas internas del panel docente.
 * Rechaza URLs absolutas, `//host` y la propia página de login.
 */
export function safeNextPath(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return "/exams";
  if (next === "/login" || next.startsWith("/login?") || next.startsWith("/login/")) return "/exams";
  return next;
}

/** Título del documento por pantalla (WCAG 2.4.2). */
export function pageTitle(screen: string | null | undefined): string {
  return screen ? `${screen} · ImprontIA` : "ImprontIA";
}
