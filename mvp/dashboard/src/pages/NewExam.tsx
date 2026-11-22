import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlertCircle, ChevronRight, Eye, FileCheck2, FileText, ListOrdered, Loader2, Minus, Plus, ShieldCheck, Upload, X } from "lucide-react";
import { api, apiErrorMessage, type ExamItem } from "../api";

const MAX_ITEMS = 30; // backend: schemas.MAX_ITEMS
const MAX_PDF_MB = 4; // backend: MAX_PDF_BYTES (límite de 4,5 MB por pedido de Vercel)
const DEFAULT_RULES = "Examen a libro cerrado, sin acceso a internet.";
import { RULE_OPTIONS, SIGNAL_OPTIONS, type RuleFlag } from "../format";
import { usePageTitle } from "../a11y";
import { SIGNAL_ICONS, SIGNAL_SHORT, Wordmark } from "../ui";

const SIGNAL_PHRASE: Record<string, string> = {
  keyboard: "tiempos de pulsación de teclas (no el texto)",
  mouse: "movimiento del mouse y clics",
  scroll: "desplazamiento de la página",
  visibility: "cambios de pestaña y de foco",
  clipboard: "cantidad de caracteres pegados",
};

/** Texto sugerido para la información previa, armado con las señales elegidas. */
export function suggestedInfo(signals: string[]): string {
  const parts = SIGNAL_OPTIONS.map((o) => o.value)
    .filter((v) => signals.includes(v))
    .map((v) => SIGNAL_PHRASE[v]);
  if (parts.length === 0) return "En esta evaluación no se registran señales de interacción.";
  const list = parts.length === 1 ? parts[0] : `${parts.slice(0, -1).join(", ")} y ${parts[parts.length - 1]}`;
  return (
    `Durante esta evaluación la plataforma registra metadatos de interacción: ${list}. ` +
    "Se usan solo para priorizar la revisión docente; ninguna decisión es automática."
  );
}

const RULE_HINT: Record<RuleFlag, string> = {
  permite_pegado: "Se sigue registrando, pero no marca la sesión para revisión.",
  permite_otras_pestanas: "Los cambios de pestaña se registran sin marcar la sesión.",
};

export default function NewExam() {
  usePageTitle("Nueva evaluación");
  const navigate = useNavigate();
  const [name, setName] = useState("");
  // Nov. 2026: el examen tiene uno o más ejercicios, escritos acá o en un PDF adjunto.
  const [mode, setMode] = useState<"texto" | "pdf">("texto");
  const [itemTexts, setItemTexts] = useState<string[]>([""]);
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [pdfCount, setPdfCount] = useState(3);
  const [dragOver, setDragOver] = useState(false);
  const [signals, setSignals] = useState<string[]>(["keyboard", "mouse", "scroll", "clipboard", "visibility"]);
  const [infoText, setInfoText] = useState(() => suggestedInfo(["keyboard", "mouse", "scroll", "clipboard", "visibility"]));
  const [infoTouched, setInfoTouched] = useState(false);
  const [rulesText, setRulesText] = useState(DEFAULT_RULES);
  const [rules, setRules] = useState<Record<RuleFlag, boolean>>({ permite_pegado: false, permite_otras_pestanas: false });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function toggleSignal(value: string) {
    setSignals((prev) => {
      const next = prev.includes(value) ? prev.filter((s) => s !== value) : [...prev, value];
      if (!infoTouched) setInfoText(suggestedInfo(next));
      return next;
    });
  }

  function pickPdf(file: File | undefined | null) {
    if (!file) return;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setError("El archivo tiene que ser un PDF.");
      return;
    }
    if (file.size > MAX_PDF_MB * 1024 * 1024) {
      setError(`El PDF supera los ${MAX_PDF_MB} MB.`);
      return;
    }
    setError(null);
    setPdfFile(file);
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setError(null);
    // Validación propia y visible arriba del formulario (antes la del navegador mostraba un
    // globo junto a un campo fuera de la pantalla y parecía que el botón no hacía nada).
    const faltan: { label: string; id: string }[] = [];
    if (!name.trim()) faltan.push({ label: "el nombre", id: "f-nombre" });
    if (mode === "texto" && itemTexts.some((t) => !t.trim()))
      faltan.push({ label: "el enunciado de cada ejercicio", id: `f-item-${itemTexts.findIndex((t) => !t.trim())}` });
    if (mode === "pdf" && !pdfFile) faltan.push({ label: "el PDF del examen", id: "f-pdf" });
    if (!infoText.trim()) faltan.push({ label: "la información previa", id: "f-info" });
    if (!rulesText.trim()) faltan.push({ label: "las reglas", id: "f-reglas" });
    if (faltan.length) {
      setError(`Falta completar ${faltan.map((f) => f.label).join(", ")}.`);
      window.setTimeout(() => document.getElementById(faltan[0].id)?.focus(), 0);
      return;
    }
    let items: ExamItem[];
    let promptText: string;
    if (mode === "texto") {
      items = itemTexts.map((t, i) => ({ id: String(i + 1), enunciado: t.trim() }));
      promptText = items.length === 1 ? items[0].enunciado : items.map((it) => `Ejercicio ${it.id}: ${it.enunciado}`).join("\n\n");
    } else {
      if (!pdfFile) return;
      items = Array.from({ length: pdfCount }, (_, i) => ({ id: String(i + 1), enunciado: "" }));
      promptText = `Enunciado en PDF (${pdfCount} ${pdfCount === 1 ? "ejercicio" : "ejercicios"}).`;
    }
    setSaving(true);
    let examId: string;
    try {
      const exam = await api.createExam({
        name,
        info_text: infoText,
        rules_text: rulesText,
        prompt_text: promptText,
        items,
        allowed_signals: signals,
        ...rules,
      });
      examId = exam.id;
    } catch (err) {
      setError(apiErrorMessage(err, "No se pudo crear la evaluación. Revisá los campos e intentá de nuevo."));
      setSaving(false);
      return;
    }
    let pdfFailed = false;
    if (mode === "pdf" && pdfFile) {
      try {
        await api.uploadExamPdf(examId, pdfFile);
      } catch {
        pdfFailed = true;
      }
    }
    navigate(`/exams/${examId}/sessions`, {
      state: pdfFailed
        ? { created: true, msg: "La evaluación se creó, pero el PDF no se pudo subir. Subilo desde Configuración." }
        : { created: true },
    });
  }

  return (
    <div className="page">
      <nav className="crumbs" aria-label="Ruta">
        <Link to="/exams">Evaluaciones</Link>
        <ChevronRight size={14} aria-hidden="true" />
        <span aria-current="page">Nueva evaluación</span>
      </nav>
      <div className="page-head">
        <div>
          <h1>Nueva evaluación</h1>
          <p className="sub">Tres pasos. A la derecha ves lo que va a leer el estudiante antes de aceptar.</p>
        </div>
      </div>

      <div className="compose">
        <form onSubmit={handleCreate} aria-label="Datos de la nueva evaluación" noValidate>
          {error && (
            <div className="alert alert-error" role="alert">
              <AlertCircle size={17} aria-hidden="true" />
              <span className="alert-body">{error}</span>
            </div>
          )}

          <section className="form-section">
            <div className="form-section-head">
              <span className="n">01</span>
              <div>
                <h2>El examen</h2>
                <p>Los ejercicios se muestran recién después de que el estudiante acepta.</p>
              </div>
            </div>
            <label className="field">
              <span className="field-label">Nombre de la evaluación</span>
              <input
                id="f-nombre"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="ej. Parcial 1 - Bases de Datos"
                aria-required="true"
              />
            </label>
            <fieldset>
              <legend className="field-label" style={{ marginBottom: 8 }}>
                ¿Cómo cargás el enunciado?
              </legend>
              <div className="mode-switch">
                <label className="mode-card">
                  <input type="radio" name="modo" checked={mode === "texto"} onChange={() => setMode("texto")} />
                  <ListOrdered size={18} aria-hidden="true" />
                  <span>
                    <strong>Escribir los ejercicios</strong>
                    <small>Uno o varios, cada uno con su campo de respuesta.</small>
                  </span>
                </label>
                <label className="mode-card">
                  <input type="radio" name="modo" checked={mode === "pdf"} onChange={() => setMode("pdf")} />
                  <FileText size={18} aria-hidden="true" />
                  <span>
                    <strong>Subir el examen en PDF</strong>
                    <small>Indicás cuántos ejercicios tiene y se arma un campo por ejercicio.</small>
                  </span>
                </label>
              </div>
            </fieldset>

            {mode === "texto" ? (
              <fieldset>
                <legend className="sr-only">Ejercicios</legend>
                {itemTexts.map((t, i) => (
                  <div key={i} className="item-editor">
                    <span className="item-n" aria-hidden="true">
                      {i + 1}
                    </span>
                    <label>
                      <span className="sr-only">Enunciado del ejercicio {i + 1}</span>
                      <textarea
                        id={`f-item-${i}`}
                        value={t}
                        onChange={(e) => setItemTexts((prev) => prev.map((x, j) => (j === i ? e.target.value : x)))}
                        placeholder={i === 0 ? "ej. Definí clave primaria y clave foránea, con un ejemplo." : `Enunciado del ejercicio ${i + 1}`}
                      />
                    </label>
                    <button
                      type="button"
                      className="btn btn-quiet btn-icon"
                      onClick={() => setItemTexts((prev) => prev.filter((_, j) => j !== i))}
                      disabled={itemTexts.length === 1}
                      aria-label={`Quitar el ejercicio ${i + 1}`}
                      title="Quitar"
                    >
                      <X size={16} aria-hidden="true" />
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  className="btn btn-ghost btn-small"
                  onClick={() => setItemTexts((prev) => [...prev, ""])}
                  disabled={itemTexts.length >= MAX_ITEMS}
                  style={{ marginLeft: 50 }}
                >
                  <Plus size={15} aria-hidden="true" />
                  Agregar ejercicio
                </button>
              </fieldset>
            ) : (
              <>
                <label
                  className={`dropzone${dragOver ? " is-over" : ""}${pdfFile ? " has-file" : ""}`}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragOver(true);
                  }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setDragOver(false);
                    pickPdf(e.dataTransfer.files?.[0]);
                  }}
                >
                  <span className="dz-icon">
                    {pdfFile ? <FileCheck2 size={19} aria-hidden="true" /> : <Upload size={19} aria-hidden="true" />}
                  </span>
                  <span style={{ minWidth: 0 }}>
                    <strong className="break-all">{pdfFile ? pdfFile.name : "Elegí el PDF o arrastralo acá"}</strong>
                    <small>
                      {pdfFile
                        ? `${pdfFile.size < 1024 * 1024 ? `${Math.max(1, Math.round(pdfFile.size / 1024))} KB` : `${(pdfFile.size / 1024 / 1024).toFixed(1).replace(".", ",")} MB`} · hacé clic para cambiarlo`
                        : `Hasta ${MAX_PDF_MB} MB. El estudiante lo ve recién después de aceptar.`}
                    </small>
                  </span>
                  <input id="f-pdf" type="file" accept="application/pdf,.pdf" onChange={(e) => pickPdf(e.target.files?.[0])} />
                </label>
                <div className="field" style={{ marginBottom: 0 }}>
                  <span className="field-label" id="n-ej">
                    ¿Cuántos ejercicios tiene el examen?
                  </span>
                  <div className="stepper-input" role="group" aria-labelledby="n-ej">
                    <button
                      type="button"
                      onClick={() => setPdfCount((n) => Math.max(1, n - 1))}
                      disabled={pdfCount <= 1}
                      aria-label="Uno menos"
                    >
                      <Minus size={15} aria-hidden="true" />
                    </button>
                    <input
                      inputMode="numeric"
                      aria-label="Cantidad de ejercicios"
                      value={pdfCount}
                      onChange={(e) => {
                        const n = parseInt(e.target.value.replace(/\D/g, ""), 10);
                        setPdfCount(Number.isFinite(n) ? Math.min(MAX_ITEMS, Math.max(1, n)) : 1);
                      }}
                    />
                    <button
                      type="button"
                      onClick={() => setPdfCount((n) => Math.min(MAX_ITEMS, n + 1))}
                      disabled={pdfCount >= MAX_ITEMS}
                      aria-label="Uno más"
                    >
                      <Plus size={15} aria-hidden="true" />
                    </button>
                  </div>
                  <span className="field-hint">El estudiante va a ver el PDF al lado de estos campos de respuesta:</span>
                  <div className="item-chips" aria-hidden="true">
                    {Array.from({ length: pdfCount }, (_, i) => (
                      <span key={i}>Ejercicio {i + 1}</span>
                    ))}
                  </div>
                </div>
              </>
            )}
          </section>

          <section className="form-section">
            <div className="form-section-head">
              <span className="n">02</span>
              <div>
                <h2>Qué se registra</h2>
                <p>Solo se capturan las señales que marques acá. El estudiante las ve antes de consentir.</p>
              </div>
            </div>
            <fieldset>
              <legend className="sr-only">Señales habilitadas para esta evaluación</legend>
              <div className="toggle-grid">
                {SIGNAL_OPTIONS.map((opt) => {
                  const Icon = SIGNAL_ICONS[opt.value];
                  return (
                    <label key={opt.value} className="toggle-card">
                      <Icon size={18} aria-hidden="true" />
                      <span>{opt.label}</span>
                      <input
                        type="checkbox"
                        checked={signals.includes(opt.value)}
                        onChange={() => toggleSignal(opt.value)}
                      />
                    </label>
                  );
                })}
              </div>
            </fieldset>
            <label className="field" style={{ marginBottom: 0 }}>
              <span className="label-row">
                <span className="field-label">Información previa para el estudiante</span>
                {infoTouched && (
                  <button
                    type="button"
                    className="btn btn-quiet btn-small"
                    onClick={() => {
                      setInfoText(suggestedInfo(signals));
                      setInfoTouched(false);
                    }}
                  >
                    Usar texto sugerido
                  </button>
                )}
              </span>
              <textarea
                id="f-info"
                value={infoText}
                onChange={(e) => {
                  setInfoText(e.target.value);
                  setInfoTouched(true);
                }}
                placeholder="Qué se va a registrar durante la evaluación y con qué finalidad."
                aria-required="true"
              />
              <span className="field-hint">
                {infoTouched
                  ? "Editado por vos."
                  : "Se completa solo según las señales elegidas. Podés editarlo."}
              </span>
            </label>
          </section>

          <section className="form-section">
            <div className="form-section-head">
              <span className="n">03</span>
              <div>
                <h2>Reglas del examen</h2>
                <p>Lo permitido no marca la sesión para revisión; aparece como «permitido por las reglas».</p>
              </div>
            </div>
            <label className="field">
              <span className="field-label">Reglas y recursos permitidos</span>
              <textarea
                id="f-reglas"
                value={rulesText}
                onChange={(e) => setRulesText(e.target.value)}
                placeholder="ej. Examen a libro cerrado, sin acceso a internet."
                aria-required="true"
              />
            </label>
            <fieldset className="switch-list">
              <legend className="sr-only">Reglas del examen</legend>
              {RULE_OPTIONS.map((opt) => (
                <label key={opt.value} className="switch-row">
                  <span>
                    {opt.label}
                    <small>{RULE_HINT[opt.value]}</small>
                  </span>
                  <input
                    type="checkbox"
                    className="switch"
                    checked={rules[opt.value]}
                    onChange={(e) => setRules((prev) => ({ ...prev, [opt.value]: e.target.checked }))}
                  />
                </label>
              ))}
            </fieldset>
          </section>

          {error && (
            <p className="alert alert-error" aria-hidden="true">
              <AlertCircle size={17} />
              <span className="alert-body">{error}</span>
            </p>
          )}
          <div className="btn-row">
            <button type="submit" className="btn btn-primary btn-large" disabled={saving}>
              {saving && <Loader2 size={16} className="spin" aria-hidden="true" />}
              Crear evaluación
            </button>
            <Link className="btn btn-quiet btn-large" to="/exams">
              Cancelar
            </Link>
          </div>
        </form>

        <aside className="preview-col" aria-label="Vista previa para el estudiante">
          <p className="preview-label">
            <Eye size={15} aria-hidden="true" />
            Así lo ve el estudiante antes de aceptar
          </p>
          <div className="preview on-black" aria-hidden="true">
            <Wordmark size={16} />
            <h3>{name || <span className="placeholder">Nombre de la evaluación</span>}</h3>
            <h4>Qué se registra</h4>
            <div className="sig-mini">
              {signals.length === 0 ? (
                <span>Ninguna señal</span>
              ) : (
                SIGNAL_OPTIONS.filter((o) => signals.includes(o.value)).map((o) => {
                  const Icon = SIGNAL_ICONS[o.value];
                  return (
                    <span key={o.value}>
                      <Icon size={13} /> {SIGNAL_SHORT[o.value]}
                    </span>
                  );
                })
              )}
            </div>
            <h4>Después de aceptar</h4>
            <p className="quote">
              {mode === "pdf"
                ? `Enunciado en PDF${pdfFile ? "" : " (falta subirlo)"} y ${pdfCount} ${pdfCount === 1 ? "campo" : "campos"} de respuesta.`
                : `${itemTexts.length} ${itemTexts.length === 1 ? "ejercicio" : "ejercicios"}, cada uno con su campo de respuesta.`}
            </p>
            <h4>Mensaje de tu docente</h4>
            <p className="quote">{infoText || <span className="placeholder">Información previa</span>}</p>
            <h4>Reglas y recursos permitidos</h4>
            <p className="quote">{rulesText || <span className="placeholder">Reglas del examen</span>}</p>
            <p className="muted" style={{ display: "flex", gap: 8, fontSize: 12 }}>
              <ShieldCheck size={14} style={{ flex: "none", marginTop: 2 }} /> No se registra qué teclas presiona ni el
              contenido que pega.
            </p>
            <div className="fake-btn">Comenzar</div>
          </div>
        </aside>
      </div>
    </div>
  );
}
