// Pruebas de la lógica pura agregada por la evaluación de usabilidad (octubre 2026).
// Ejecutar con: npm test
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  clearDraft,
  draftKey,
  loadDraft,
  normalizeJoinCode,
  saveDraft,
  studentExamUrl,
  type ExamDraft,
} from "../src/examDraft.ts";
import {
  formatMetricValue,
  metricName,
  pageTitle,
  safeNextPath,
  sessionTypeLabel,
  sortSessionsForReview,
} from "../src/format.ts";

class MemStorage {
  data = new Map<string, string>();
  getItem(k: string) {
    return this.data.has(k) ? this.data.get(k)! : null;
  }
  setItem(k: string, v: string) {
    this.data.set(k, v);
  }
  removeItem(k: string) {
    this.data.delete(k);
  }
}

const draft: Omit<ExamDraft, "savedAt"> = {
  examCode: "AB12CD",
  sessionId: "s-1",
  token: "tok",
  startedAt: 1_000,
  participantId: "P-017",
  consent: true,
  promptText: "Consigna",
  allowedSignals: ["keyboard"],
  answer: "borrador",
  nextSeq: 4,
};

test("borrador: se guarda, se recupera con el mismo código (sin importar mayúsculas) y se borra", () => {
  const st = new MemStorage();
  assert.equal(saveDraft(draft, st, 5_000), true);
  const back = loadDraft("ab12cd", st);
  assert.deepEqual(back, { ...draft, savedAt: 5_000 });
  assert.equal(loadDraft("OTRO", st), null);
  clearDraft("AB12CD", st);
  assert.equal(loadDraft("AB12CD", st), null);
});

test("borrador: datos corruptos, sin consentimiento o de otro examen no se retoman", () => {
  const st = new MemStorage();
  st.setItem(draftKey("AB12CD"), "{no es json");
  assert.equal(loadDraft("AB12CD", st), null);
  st.setItem(draftKey("AB12CD"), JSON.stringify({ ...draft, consent: false }));
  assert.equal(loadDraft("AB12CD", st), null);
  st.setItem(draftKey("AB12CD"), JSON.stringify({ ...draft, examCode: "ZZZZZZ" }));
  assert.equal(loadDraft("AB12CD", st), null);
  st.setItem(draftKey("AB12CD"), JSON.stringify({ ...draft, token: "" }));
  assert.equal(loadDraft("AB12CD", st), null);
  // un nextSeq inválido vuelve a 1
  st.setItem(draftKey("AB12CD"), JSON.stringify({ ...draft, nextSeq: -3 }));
  assert.equal(loadDraft("AB12CD", st)?.nextSeq, 1);
});

test("borrador: sin almacenamiento o con errores del navegador no rompe", () => {
  assert.equal(loadDraft("AB12CD", null), null);
  assert.equal(saveDraft(draft, null), false);
  const broken = {
    getItem() {
      throw new Error("bloqueado");
    },
    setItem() {
      throw new Error("cuota");
    },
    removeItem() {
      throw new Error("bloqueado");
    },
  };
  assert.equal(loadDraft("AB12CD", broken), null);
  assert.equal(saveDraft(draft, broken), false);
  assert.doesNotThrow(() => clearDraft("AB12CD", broken));
});

test("código de examen y enlace absoluto para estudiantes", () => {
  assert.equal(normalizeJoinCode("  ab 12cd "), "AB12CD");
  assert.equal(normalizeJoinCode("   "), "");
  assert.equal(studentExamUrl("https://improntia.app/", "AB12CD"), "https://improntia.app/exam/AB12CD");
  assert.equal(studentExamUrl("http://localhost:5180", "AB12CD"), "http://localhost:5180/exam/AB12CD");
});

test("sesiones: las que requieren revisión van primero y luego las más recientes", () => {
  const s = [
    { id: "a", needs_review: false, started_at: "2026-10-01T10:00:00+00:00" },
    { id: "b", needs_review: true, started_at: "2026-10-01T09:00:00+00:00" },
    { id: "c", needs_review: false, started_at: "2026-10-01T11:00:00+00:00" },
    { id: "d", needs_review: true, started_at: "2026-10-01T12:00:00+00:00" },
  ];
  assert.deepEqual(sortSessionsForReview(s).map((x) => x.id), ["d", "b", "c", "a"]);
  assert.deepEqual(s.map((x) => x.id), ["a", "b", "c", "d"]); // no muta la entrada
});

test("login: solo se vuelve a rutas internas", () => {
  assert.equal(safeNextPath("/sessions/123"), "/sessions/123");
  assert.equal(safeNextPath("/exams/1/sessions?tab=panorama"), "/exams/1/sessions?tab=panorama");
  for (const bad of [null, undefined, "", "https://evil.com", "//evil.com", "/\\evil.com", "/login", "/login?next=/x", "exams"]) {
    assert.equal(safeNextPath(bad), "/exams");
  }
});

test("vocabulario para el docente: métricas, unidades, tipo de sesión y título", () => {
  assert.equal(metricName("paste_chars_total"), "Caracteres pegados");
  assert.equal(metricName("focus_loss_duration_total_ms"), "Tiempo con la pestaña oculta");
  assert.equal(metricName("metrica_nueva_x"), "metrica nueva x");
  assert.equal(formatMetricValue("paste_chars_total", 264), "264");
  assert.equal(formatMetricValue("focus_loss_duration_total_ms", 3_500), "3,5 s");
  assert.equal(formatMetricValue("idle_ratio", 0.25), "25 %");
  assert.equal(formatMetricValue("x", null), "—");
  assert.equal(sessionTypeLabel("exam"), "Examen");
  assert.equal(sessionTypeLabel("otro"), "otro");
  assert.equal(pageTitle("Evaluaciones"), "Evaluaciones · ImprontIA");
  assert.equal(pageTitle(null), "ImprontIA");
});
