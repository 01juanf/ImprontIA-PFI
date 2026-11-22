// Sesión de examen en curso guardada en el navegador del estudiante (evaluación de usabilidad,
// problema 1). Si la página se recarga o el estudiante sale y vuelve con el mismo enlace, se
// retoma la MISMA sesión (sin crear otra) con el borrador de la respuesta.
//
// Se usa sessionStorage: vive solo en esa pestaña y se borra al cerrarla. Se guarda el token
// opaco de la sesión (ya estaba en memoria) y el borrador; nunca el contenido del portapapeles.
// Lógica pura con un Storage inyectable para probarla con `node --test` (tests/examDraft.test.ts).

export interface ExamDraft {
  examCode: string;
  sessionId: string;
  token: string;
  startedAt: number; // epoch ms: los `t` de los eventos siguen siendo relativos al mismo inicio
  participantId: string;
  consent: boolean;
  promptText: string;
  allowedSignals: string[];
  answer: string;
  // Nov. 2026: ejercicios del examen y respuesta de cada uno (opcionales: borradores anteriores).
  items?: { id: string; enunciado: string }[] | null;
  tienePdf?: boolean;
  answers?: Record<string, string>;
  nextSeq: number; // próximo número de lote (el backend ignora los seq ya aplicados)
  savedAt: number;
}

type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;

const PREFIX = "improntia_examen_";

export function draftKey(examCode: string): string {
  return PREFIX + examCode.trim().toUpperCase();
}

function storage(s?: StorageLike | null): StorageLike | null {
  if (s !== undefined) return s;
  try {
    return typeof sessionStorage === "undefined" ? null : sessionStorage;
  } catch {
    return null; // acceso bloqueado (modo privado estricto, iframes sandbox)
  }
}

function isDraft(v: unknown, examCode: string): v is ExamDraft {
  if (!v || typeof v !== "object") return false;
  const d = v as Record<string, unknown>;
  return (
    typeof d.sessionId === "string" && d.sessionId.length > 0 &&
    typeof d.token === "string" && d.token.length > 0 &&
    typeof d.startedAt === "number" &&
    typeof d.examCode === "string" && d.examCode.toUpperCase() === examCode.trim().toUpperCase() &&
    d.consent === true &&
    typeof d.answer === "string" &&
    Array.isArray(d.allowedSignals)
  );
}

export function loadDraft(examCode: string, s?: StorageLike | null): ExamDraft | null {
  const st = storage(s);
  if (!st) return null;
  try {
    const raw = st.getItem(draftKey(examCode));
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!isDraft(parsed, examCode)) return null;
    return {
      ...parsed,
      promptText: typeof parsed.promptText === "string" ? parsed.promptText : "",
      participantId: typeof parsed.participantId === "string" ? parsed.participantId : "",
      nextSeq: typeof parsed.nextSeq === "number" && parsed.nextSeq >= 1 ? Math.floor(parsed.nextSeq) : 1,
    };
  } catch {
    return null;
  }
}

/** Guarda (o actualiza) el borrador. Devuelve false si el navegador no lo permitió. */
export function saveDraft(draft: Omit<ExamDraft, "savedAt">, s?: StorageLike | null, now = Date.now()): boolean {
  const st = storage(s);
  if (!st) return false;
  try {
    st.setItem(draftKey(draft.examCode), JSON.stringify({ ...draft, savedAt: now }));
    return true;
  } catch {
    return false; // cuota llena o almacenamiento bloqueado: se sigue sin persistir
  }
}

export function clearDraft(examCode: string, s?: StorageLike | null): void {
  const st = storage(s);
  if (!st) return;
  try {
    st.removeItem(draftKey(examCode));
  } catch {
    // nada que hacer
  }
}

/** Normaliza lo que el estudiante tipea como código de examen (sin espacios, mayúsculas). */
export function normalizeJoinCode(input: string): string {
  return input.replace(/\s+/g, "").toUpperCase();
}

/** Enlace absoluto que el docente comparte con los estudiantes. */
export function studentExamUrl(origin: string, joinCode: string): string {
  return `${origin.replace(/\/+$/, "")}/exam/${encodeURIComponent(joinCode)}`;
}

// Nov. 2026: marca de «ya entregaste» en esta pestaña, para que volver a abrir el enlace no
// ofrezca empezar otra sesión como si nada (se puede empezar otra a propósito).
const DELIVERED_PREFIX = "improntia_entregado_";

export function markDelivered(examCode: string, s?: StorageLike | null): void {
  try {
    storage(s)?.setItem(DELIVERED_PREFIX + examCode.trim().toUpperCase(), String(Date.now()));
  } catch {
    // sin almacenamiento: no pasa nada
  }
}

export function wasDelivered(examCode: string, s?: StorageLike | null): boolean {
  try {
    return Boolean(storage(s)?.getItem(DELIVERED_PREFIX + examCode.trim().toUpperCase()));
  } catch {
    return false;
  }
}
