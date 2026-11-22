// Cliente de API del dashboard docente. Sin librerías extra (fetch nativo):
// el alcance del MVP no justifica React Query u otra capa adicional todavía.

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8010";

const TOKEN_KEY = "improntia_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

/** Evento global que se emite cuando el backend rechaza el token docente (401). */
export const UNAUTHORIZED_EVENT = "improntia:no-autorizado";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  // FormData (subida del PDF): el navegador arma el Content-Type con el boundary.
  if (options.body instanceof FormData) delete headers["Content-Type"];

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...options, headers });
  } catch {
    // Sin respuesta: el backend no está levantado, la URL es otra o el navegador bloqueó CORS.
    throw new ApiError(0, `No se pudo conectar con el servidor (${API_URL}).`);
  }

  // Evaluación de usabilidad (problema 12): un token docente vencido o inválido lleva al login
  // (Layout escucha el evento y conserva la ruta pedida). No aplica al login ni a las
  // llamadas del estudiante, que se autentican con X-Session-Token.
  // En DELETE /auth/me un 401 significa «contraseña incorrecta», no un token vencido.
  if (res.status === 401 && token && path !== "/auth/login" && path !== "/auth/me" && !headers["X-Session-Token"]) {
    clearToken();
    if (typeof window !== "undefined") window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // sin body JSON, se usa el statusText
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

/** Descarga binaria (PDF del enunciado) con el mismo manejo de errores que request(). */
async function requestBlob(path: string, headers: Record<string, string> = {}): Promise<Blob> {
  const token = getToken();
  const h: Record<string, string> = { ...headers };
  if (token && !h["X-Session-Token"]) h["Authorization"] = `Bearer ${token}`;
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { headers: h });
  } catch {
    throw new ApiError(0, `No se pudo conectar con el servidor (${API_URL}).`);
  }
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  return res.blob();
}

/** Mensaje para el docente según el error de la API. */
export function apiErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError && err.status === 0)
    return `${err.message} Revisá que el backend esté levantado y recargá la página.`;
  return fallback;
}

// ---- Tipos (reflejan app/schemas.py del backend) ----

export interface Policy {
  id: string;
  info_text: string;
  rules_text: string;
  allowed_signals: string[];
  permite_pegado: boolean; // Incremento 12: reglas del examen
  permite_otras_pestanas: boolean;
  retencion_dias?: number | null; // plazo de conservación (días), null = sin plazo
  created_at: string;
}

export interface ExamRules {
  permite_pegado?: boolean;
  permite_otras_pestanas?: boolean;
  retencion_dias?: number | null;
}

// Panorama de la evaluación (Incremento 12, R1): GET /exams/{id}/panorama
export interface PanoramaMetric {
  metric: string;
  n: number;
  mediana: number | null;
  p25: number | null;
  p75: number | null;
}

export interface Panorama {
  exam_id: string;
  n_sesiones: number;
  sesiones_requieren_revision: number;
  metricas: PanoramaMetric[];
  indicadores: { kind: string; sesiones: number; permitidas_por_reglas: number; porcentaje: number }[];
  modelo: { sesiones_marcadas: number; porcentaje: number; metricas_frecuentes: { metric: string; sesiones: number }[] };
  cobertura?: {
    evaluacion_cerrada: boolean;
    sesiones_evaluadas: number;
    sesiones_no_evaluadas: number;
    sesiones_pendientes: number;
  };
}

export interface Exam {
  id: string;
  name: string;
  join_code: string;
  prompt_text: string;
  created_at: string;
  cerrada_at?: string | null; // Incremento 16: cierre con análisis de la cohorte
  items?: ExamItem[] | null; // nov. 2026: ejercicios; null = una sola consigna
  tiene_pdf?: boolean;
  pdf_nombre?: string | null;
  current_policy: Policy;
  policy_version: number; // 1 = original; cada edición crea una versión nueva (RNF04)
}

export interface ExamItem {
  id: string;
  enunciado: string;
}

export interface ExamPublicInfo {
  name: string;
  info_text: string;
  rules_text: string;
  allowed_signals: string[];
  cerrada?: boolean; // Incremento 16: ya no admite sesiones nuevas
}

export type ReviewStatus = "sin_revision" | "revisada" | "validacion_pendiente";

export interface SessionSummary {
  id: string;
  exam_id: string;
  exam_name: string;
  participant_id: string;
  session_type: string;
  status: string;
  needs_review: boolean;
  started_at: string;
  ended_at: string | null;
  review_status: ReviewStatus; // derivado de la última revisión (RF11/HU08)
  last_review_at: string | null;
  last_review_notes: string | null;
  estado_modelo: "pendiente" | "no_evaluada" | "sin_marca" | "con_marca";
  // Rediseño (nov. 2026): tipos de indicador de la sesión, para la huella de la lista.
  indicadores?: { kind: string; level: string; prioriza: boolean }[];
}

export interface Metric {
  id: string;
  name: string;
  value: number;
  item_ref: string | null;
}

export interface Indicator {
  id: string;
  kind: string;
  level: "low" | "medium" | "high";
  description: string;
  explanation: Record<string, unknown>;
  metric_ids: string[];
  computed_at: string;
}

export interface Review {
  id: string;
  action: string;
  notes: string | null;
  indicator_ids: string[];
  created_at: string;
  teacher_email: string | null;
}

export interface SessionDetail extends SessionSummary {
  context: Record<string, unknown>;
  metrics: Metric[];
  indicators: Indicator[];
  event_count: number;
  reviews: Review[]; // historial, más antigua primero
  procesada: boolean;
  respuesta: string | null;
  items?: ExamItem[] | null;
  respuestas?: Record<string, string> | null;
  tiene_pdf?: boolean;
}

export interface SessionStartResponse {
  session_id: string;
  session_token: string;
  allowed_signals: string[];
  info_text: string;
  rules_text: string;
  prompt_text: string;
  items?: ExamItem[] | null;
  tiene_pdf?: boolean;
}

// ---- Endpoints ----

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  listExams: () => request<Exam[]>("/exams"),

  createExam: (payload: {
    name: string;
    info_text: string;
    rules_text: string;
    prompt_text: string;
    allowed_signals: string[];
    items?: ExamItem[] | null;
  } & ExamRules) => request<Exam>("/exams", { method: "POST", body: JSON.stringify(payload) }),

  // Nov. 2026: enunciado en PDF (hasta 4 MB, límite de Vercel).
  uploadExamPdf: (examId: string, file: File) => {
    const fd = new FormData();
    fd.append("archivo", file);
    return request<Exam>(`/exams/${examId}/pdf`, { method: "PUT", body: fd });
  },
  getExamPdf: (examId: string) => requestBlob(`/exams/${examId}/pdf`),
  getSessionPdf: (sessionId: string, sessionToken: string) =>
    requestBlob(`/sessions/${sessionId}/enunciado.pdf`, { "X-Session-Token": sessionToken }),

  getExam: (examId: string) => request<Exam>(`/exams/${examId}`),

  getPanorama: (examId: string) => request<Panorama>(`/exams/${examId}/panorama`),

  // Incremento 16: cierra la evaluación y analiza la cohorte completa con el modelo.
  closeExam: (examId: string) => request<Exam>(`/exams/${examId}/cerrar`, { method: "POST" }),

  // RF17: elimina la evaluación con todas sus sesiones y datos (no se puede deshacer).
  deleteExam: (examId: string) => request<void>(`/exams/${examId}`, { method: "DELETE" }),

  // RF17: elimina la cuenta del docente con todas sus evaluaciones; pide la contraseña.
  deleteAccount: (password: string) =>
    request<void>("/auth/me", { method: "DELETE", body: JSON.stringify({ password }) }),

  // RF17: elimina una sesión con todos sus datos.
  deleteSession: (sessionId: string) => request<void>(`/sessions/${sessionId}`, { method: "DELETE" }),

  // Crea una NUEVA versión de la política (RNF04): las sesiones ya iniciadas conservan la suya.
  updatePolicy: (examId: string, payload: { info_text: string; rules_text: string; allowed_signals: string[] } & ExamRules) =>
    request<Policy>(`/exams/${examId}/policy`, { method: "POST", body: JSON.stringify(payload) }),

  listSessions: (params: { exam_id?: string; needs_review?: boolean; review_status?: ReviewStatus } = {}) => {
    const qs = new URLSearchParams();
    if (params.exam_id) qs.set("exam_id", params.exam_id);
    if (params.needs_review !== undefined) qs.set("needs_review", String(params.needs_review));
    if (params.review_status) qs.set("review_status", params.review_status);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return request<SessionSummary[]>(`/sessions${suffix}`);
  },

  getSession: (sessionId: string) => request<SessionDetail>(`/sessions/${sessionId}`),

  createReview: (sessionId: string, action: string, notes: string | null, indicatorIds: string[] = []) =>
    request<Review>(`/sessions/${sessionId}/reviews`, {
      method: "POST",
      body: JSON.stringify({ action, notes, indicator_ids: indicatorIds }),
    }),

  // ---- Endpoints públicos (sin JWT docente): usados por la vista de examen del estudiante ----

  getExamPublicInfo: (joinCode: string) => request<ExamPublicInfo>(`/exams/${joinCode}/info`),

  startSession: (payload: {
    exam_code: string;
    participant_id: string;
    session_type: string;
    context: Record<string, unknown>;
    consent_given: boolean;
    condicion_simulacion?: string; // P03: solo en modo simulación; el docente no la ve
  }) => request<SessionStartResponse>("/sessions/start", { method: "POST", body: JSON.stringify(payload) }),

  postEvents: (
    sessionId: string,
    sessionToken: string,
    seq: number,
    events: Record<string, unknown>[],
    opts: { keepalive?: boolean } = {}
  ) =>
    request<{ stored: number }>(`/sessions/${sessionId}/events`, {
      method: "POST",
      headers: { "X-Session-Token": sessionToken },
      body: JSON.stringify({ seq, events }),
      keepalive: opts.keepalive,
    }),

  // Incremento 16: cierre idempotente; `procesada` confirma que el servidor terminó el procesamiento.
  endSession: (sessionId: string, sessionToken: string, respuesta?: string, respuestas?: Record<string, string> | null) =>
    request<{ status: string; needs_review: boolean; procesada: boolean }>(`/sessions/${sessionId}/end`, {
      method: "POST",
      headers: { "X-Session-Token": sessionToken },
      body: JSON.stringify({ respuesta: respuesta ?? null, respuestas: respuestas ?? null }),
    }),
};
