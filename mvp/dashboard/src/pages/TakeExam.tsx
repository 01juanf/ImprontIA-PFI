import { useEffect, useRef, useState, type FormEvent } from "react";
import type React from "react";
import type { ExamItem } from "../api";
import { AlertCircle, Check, CloudOff, Keyboard, Loader2, RotateCcw, ShieldCheck } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api, type ExamPublicInfo } from "../api";
import { attachCapture } from "../capture";
import { focusMainHeading, usePageTitle } from "../a11y";
import { ConfirmDialog, Loading, SIGNAL_ICONS, SIGNAL_SHORT, Wordmark } from "../ui";
import { clearDraft, loadDraft, markDelivered, saveDraft, wasDelivered } from "../examDraft";
import {
  SIGNAL_STUDENT_DESCRIPTIONS,
  SIMULATION_CONDITIONS,
  isSimulationMode,
  signalLabel,
  simulationConditionToSend,
} from "../format";
import { DEFAULT_SYNC_CONFIG, SyncQueue, isRejectedBatchStatus } from "../syncQueue";

// Reintentos al finalizar: si la red falla justo al entregar, se insiste unas pocas
// veces antes de cerrar la sesión (Incremento 10).
const FINISH_RETRY_DELAYS_MS = [1_000, 2_000, 4_000];

type Phase = "loading" | "not_found" | "closed" | "delivered" | "consent" | "active" | "finishing" | "finished";

// Incremento 16: estados del cierre. La entrega solo se confirma cuando el servidor responde
// que la sesión quedó finalizada Y procesada; si algo falla, se puede reintentar sin riesgo
// (el cierre es idempotente) y la respuesta sigue en esta pantalla.
type FinishStep = "sending" | "closing" | "error_sync" | "error_close";

interface SyncView {
  sent: number;
  pending: number;
  failures: number;
  retryInS: number;
  dropped: number;
  rejected: number;
}

const sleep = (ms: number) => new Promise((r) => window.setTimeout(r, ms));

export default function TakeExam() {
  const { joinCode = "" } = useParams<{ joinCode: string }>();
  const [phase, setPhase] = useState<Phase>("loading");
  const [examInfo, setExamInfo] = useState<ExamPublicInfo | null>(null);
  const [participantId, setParticipantId] = useState("");
  // P03: modo simulación (enlace con ?simulacion=1). La condición no la ve el docente.
  const [simulation] = useState(() => isSimulationMode(window.location.search));
  const [condition, setCondition] = useState("");
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const [promptText, setPromptText] = useState("");
  const [answer, setAnswer] = useState("");
  // Nov. 2026: varios ejercicios (con o sin PDF de enunciado), una respuesta por ejercicio.
  const [items, setItems] = useState<ExamItem[] | null>(null);
  const [tienePdf, setTienePdf] = useState(false);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfError, setPdfError] = useState(false);
  const [sync, setSync] = useState<SyncView>({ sent: 0, pending: 0, failures: 0, retryInS: 0, dropped: 0, rejected: 0 });
  const [unsentAtFinish, setUnsentAtFinish] = useState(0);
  const [finishStep, setFinishStep] = useState<FinishStep>("sending");
  // Evaluación de usabilidad (problema 4): la entrega pide una confirmación en línea.
  const [confirmFinish, setConfirmFinish] = useState(false);
  // Problema 1: aviso cuando se retomó una sesión guardada en esta pestaña.
  const [resumed, setResumed] = useState(false);

  const sessionRef = useRef<{ id: string; token: string; startedAt: number } | null>(null);
  const queueRef = useRef(new SyncQueue());
  const phaseRef = useRef<Phase>("loading");
  const deliveredRef = useRef(false);
  const answerRef = useRef("");
  const answersRef = useRef<Record<string, string>>({});
  const draftMetaRef = useRef<{
    participantId: string;
    promptText: string;
    allowedSignals: string[];
    items?: ExamItem[] | null;
    tienePdf?: boolean;
  } | null>(null);
  const containerRef = useRef<HTMLElement | null>(null);
  const detachRef = useRef<(() => void) | null>(null);
  const timerRef = useRef<number | null>(null);
  const flushingRef = useRef(false);
  const stoppedRef = useRef(false);

  phaseRef.current = phase;
  usePageTitle(
    phase === "not_found"
      ? "Código no encontrado"
      : phase === "active"
        ? `Rindiendo: ${examInfo?.name ?? "examen"}`
        : phase === "finished"
          ? "Entrega confirmada"
          : phase === "finishing"
            ? "Entregando"
            : examInfo?.name ?? "Examen",
  );

  // Foco en el encabezado de cada paso (consentimiento → consigna → entrega).
  useEffect(() => {
    if (phase !== "loading" && phase !== "consent") focusMainHeading(containerRef.current);
  }, [phase, finishStep]);

  /** Guarda en sessionStorage la sesión activa y el borrador (problema 1). */
  function persistDraft() {
    const session = sessionRef.current;
    const meta = draftMetaRef.current;
    if (!session || !meta || deliveredRef.current) return;
    saveDraft({
      examCode: joinCode,
      sessionId: session.id,
      token: session.token,
      startedAt: session.startedAt,
      participantId: meta.participantId,
      consent: true,
      promptText: meta.promptText,
      allowedSignals: meta.allowedSignals,
      answer: answerRef.current,
      items: meta.items ?? null,
      tienePdf: meta.tienePdf ?? false,
      answers: answersRef.current,
      nextSeq: queueRef.current.nextSeqValue,
    });
  }

  /** Arranca (o re-engancha, al retomar) la captura y el envío periódico. */
  function beginCapture(session: { id: string; token: string; startedAt: number }, allowedSignals: string[]) {
    sessionRef.current = session;
    stoppedRef.current = false;
    detachRef.current = attachCapture(session.startedAt, allowedSignals, (evt) => {
      queueRef.current.push(evt);
    });
    scheduleNext();
  }

  useEffect(() => {
    let cancelled = false;
    api
      .getExamPublicInfo(joinCode)
      .then((info) => {
        if (cancelled) return;
        setExamInfo(info);
        const draft = loadDraft(joinCode);
        if (draft && !sessionRef.current) {
          // Recarga o regreso con el mismo enlace: se retoma la MISMA sesión, sin crear otra.
          queueRef.current = new SyncQueue(DEFAULT_SYNC_CONFIG, draft.nextSeq);
          draftMetaRef.current = {
            participantId: draft.participantId,
            promptText: draft.promptText,
            allowedSignals: draft.allowedSignals,
            items: draft.items ?? null,
            tienePdf: draft.tienePdf ?? false,
          };
          answerRef.current = draft.answer;
          answersRef.current = draft.answers ?? {};
          setItems(draft.items ?? null);
          setTienePdf(Boolean(draft.tienePdf));
          setAnswers(draft.answers ?? {});
          setParticipantId(draft.participantId);
          setConsent(true);
          setPromptText(draft.promptText);
          setAnswer(draft.answer);
          setResumed(true);
          beginCapture({ id: draft.sessionId, token: draft.token, startedAt: draft.startedAt }, draft.allowedSignals);
          setPhase("active");
          return;
        }
        if (info.cerrada) setPhase("closed");
        else if (wasDelivered(joinCode)) setPhase("delivered");
        else setPhase("consent");
      })
      .catch(() => {
        if (!cancelled) setPhase("not_found");
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [joinCode]);

  function nowT(): number {
    return sessionRef.current ? Date.now() - sessionRef.current.startedAt : 0;
  }

  function publish(retryMs = 0) {
    const q = queueRef.current;
    setSync({
      sent: q.sentEvents,
      pending: q.pendingBatches,
      failures: q.consecutiveFailures,
      retryInS: Math.round(retryMs / 1000),
      dropped: q.droppedSinceLastReport,
      rejected: q.rejectedEvents,
    });
  }

  /**
   * Envía los lotes pendientes en orden. Ante una falla deja el resto en cola (el lote
   * conserva su número de secuencia, así el backend descarta un reenvío ya aplicado) y
   * devuelve false para que el próximo intento se espacie con backoff.
   */
  async function flush(finalAttempt = false): Promise<boolean> {
    const session = sessionRef.current;
    const q = queueRef.current;
    if (!session || flushingRef.current) return q.pendingBatches === 0;
    flushingRef.current = true;
    try {
      q.seal();
      persistDraft(); // el próximo seq queda guardado antes de enviar
      for (let batch = q.peek(); batch; batch = q.peek()) {
        try {
          await api.postEvents(session.id, session.token, batch.seq, batch.events, { keepalive: finalAttempt });
          q.ack(nowT());
        } catch (err) {
          if (err instanceof ApiError && isRejectedBatchStatus(err.status)) {
            // Lote inválido (422): reenviarlo no cambia nada y bloquearía la cola. Se descarta,
            // se cuenta como perdido (queda registrado para el docente) y se sigue con el resto.
            console.warn(`Lote ${batch.seq} rechazado por el servidor (${batch.events.length} eventos):`, err.message);
            q.reject(nowT());
          } else {
            q.fail(nowT());
            return false;
          }
        }
        q.seal(); // los eventos de estado que agregan ack()/reject() salen en este mismo ciclo
        persistDraft();
      }
      return true;
    } finally {
      flushingRef.current = false;
    }
  }

  function scheduleNext() {
    if (stoppedRef.current) return;
    const delay = queueRef.current.nextDelay();
    publish(delay);
    timerRef.current = window.setTimeout(async () => {
      await flush();
      scheduleNext();
    }, delay);
  }

  async function handleStart(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!participantId.trim()) {
      setError("Ingresá tu código de participante.");
      return;
    }
    if (!consent) {
      setError("Se requiere confirmar el consentimiento para iniciar.");
      return;
    }
    if (simulation && !simulationConditionToSend(true, condition)) {
      setError("Elegí la condición de esta simulación.");
      return;
    }

    setStarting(true);
    try {
      const res = await api.startSession({
        exam_code: joinCode,
        participant_id: participantId.trim(),
        session_type: "exam",
        context: {},
        consent_given: true,
        condicion_simulacion: simulationConditionToSend(simulation, condition),
      });
      const startedAt = Date.now();
      draftMetaRef.current = {
        participantId: participantId.trim(),
        promptText: res.prompt_text,
        allowedSignals: res.allowed_signals,
        items: res.items ?? null,
        tienePdf: Boolean(res.tiene_pdf),
      };
      setPromptText(res.prompt_text);
      setItems(res.items?.length ? res.items : null);
      setTienePdf(Boolean(res.tiene_pdf));
      beginCapture({ id: res.session_id, token: res.session_token, startedAt }, res.allowed_signals);
      persistDraft();

      setPhase("active");
    } catch (err) {
      // Incremento 16: una evaluación cerrada por el docente ya no admite sesiones (409).
      setError(
        err instanceof ApiError && err.status === 409
          ? "Esta evaluación ya fue cerrada por el docente: no admite sesiones nuevas."
          : "No se pudo iniciar la sesión. Verificá tu conexión e intentá de nuevo.",
      );
    } finally {
      setStarting(false);
    }
  }

  // Si el navegador avisa que volvió la conexión, no se espera al próximo intento del backoff
  // (que puede estar hasta 60 s lejos): se reintenta enseguida y se retoma el ritmo normal.
  useEffect(() => {
    function handleOnline() {
      if (!sessionRef.current || stoppedRef.current || queueRef.current.consecutiveFailures === 0) return;
      if (timerRef.current) window.clearTimeout(timerRef.current);
      flush().then(scheduleNext);
    }
    window.addEventListener("online", handleOnline);
    return () => window.removeEventListener("online", handleOnline);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Último intento de sincronizar si se cierra la pestaña con la sesión activa, y aviso del
  // navegador mientras la respuesta no se entregó (problema 1). El borrador ya quedó guardado.
  useEffect(() => {
    function handleBeforeUnload(e: BeforeUnloadEvent) {
      if (sessionRef.current && !stoppedRef.current) flush(true);
      if (phaseRef.current === "active" || phaseRef.current === "finishing") {
        persistDraft();
        e.preventDefault();
        e.returnValue = ""; // navegadores que todavía lo requieren
      }
    }
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    return () => {
      stoppedRef.current = true;
      if (timerRef.current) window.clearTimeout(timerRef.current);
      if (detachRef.current) detachRef.current();
    };
  }, []);

  function stopCapture() {
    stoppedRef.current = true;
    if (timerRef.current) window.clearTimeout(timerRef.current);
    if (detachRef.current) {
      detachRef.current();
      detachRef.current = null;
    }
  }

  async function sendPending(): Promise<boolean> {
    while (flushingRef.current) await sleep(50); // un envío programado puede estar en curso
    let ok = await flush();
    for (const wait of FINISH_RETRY_DELAYS_MS) {
      if (ok) break;
      await sleep(wait);
      ok = await flush();
    }
    publish();
    setUnsentAtFinish(ok ? 0 : queueRef.current.bufferedCount);
    return ok;
  }

  async function closeSession() {
    const session = sessionRef.current;
    if (!session) return;
    setFinishStep("closing");
    try {
      const res = items
        ? await api.endSession(session.id, session.token, undefined, answersRef.current)
        : await api.endSession(session.id, session.token, answer);
      if (res.procesada) {
        deliveredRef.current = true;
        clearDraft(joinCode); // entrega confirmada: ya no hay nada que retomar
        markDelivered(joinCode);
        setPhase("finished");
        return;
      }
    } catch {
      // se informa abajo y se ofrece reintentar: el cierre es idempotente
    }
    setFinishStep("error_close");
  }

  function updateAnswer(value: string) {
    setAnswer(value);
    answerRef.current = value;
    persistDraft();
  }

  function updateItemAnswer(id: string, value: string) {
    const next = { ...answersRef.current, [id]: value };
    answersRef.current = next;
    setAnswers(next);
    persistDraft();
  }

  // Enunciado en PDF: se descarga con el token de la sesión (solo después del consentimiento).
  useEffect(() => {
    if (phase !== "active" || !tienePdf || pdfUrl || !sessionRef.current) return;
    const s = sessionRef.current;
    let url: string | null = null;
    api
      .getSessionPdf(s.id, s.token)
      .then((blob) => {
        url = URL.createObjectURL(new Blob([blob], { type: "application/pdf" }));
        setPdfUrl(url);
      })
      .catch(() => setPdfError(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, tienePdf]);

  async function handleFinish(skipPending = false) {
    setConfirmFinish(false);
    persistDraft();
    stopCapture();
    setPhase("finishing");
    if (!skipPending) {
      setFinishStep("sending");
      if (!(await sendPending())) {
        setFinishStep("error_sync");
        return;
      }
    }
    await closeSession();
  }

  const step =
    phase === "not_found" ? 1 : phase === "consent" || phase === "closed" ? 2 : phase === "active" ? 3 : 4;

  const bar = (right?: React.ReactNode) => (
    <header className="student-bar">
      <div className="student-bar-left">
        <Wordmark />
        {examInfo && <span className="sep" aria-hidden="true" />}
        {examInfo && <span className="exam-name">{examInfo.name}</span>}
      </div>
      <div className="student-bar-right">
        {right ?? <StudentStepper step={step} />}
      </div>
    </header>
  );

  if (phase === "loading") {
    return (
      <div className="student on-black">
        {bar()}
        <main className="student-main">
          <Loading />
        </main>
      </div>
    );
  }

  if (phase === "not_found") {
    return (
      <div className="student on-black glow">
        {bar()}
        <main className="student-main enter" ref={containerRef}>
          <span className="eyebrow">Código {joinCode.toUpperCase()}</span>
          <h1>No encontramos ese examen</h1>
          <p className="lead">Revisá el código con tu docente: son 6 caracteres, letras y números.</p>
          <div className="btn-row" style={{ marginTop: 24 }}>
            <Link className="btn btn-primary btn-large" to="/rendir">
              Ingresar otro código
            </Link>
          </div>
        </main>
      </div>
    );
  }

  if (phase === "closed" && examInfo) {
    return (
      <div className="student on-black glow">
        {bar()}
        <main className="student-main enter" ref={containerRef}>
          <span className="eyebrow">Evaluación cerrada</span>
          <h1>{examInfo.name}</h1>
          <p className="lead">
            Tu docente ya cerró esta evaluación y no admite entregas nuevas. Si creés que es un error, escribile.
          </p>
          <div className="btn-row" style={{ marginTop: 24 }}>
            <Link className="btn btn-ghost btn-large" to="/rendir">
              Ingresar otro código
            </Link>
          </div>
        </main>
      </div>
    );
  }

  if (phase === "delivered" && examInfo) {
    return (
      <div className="student on-black glow">
        {bar()}
        <main className="result" ref={containerRef}>
          <div className="result-inner enter">
            <span className="mark-ok">
              <Check size={30} aria-hidden="true" />
            </span>
            <h1>Ya entregaste este examen</h1>
            <p className="muted">
              Desde esta pestaña ya se confirmó una entrega de «{examInfo.name}». No hace falta hacer nada más.
            </p>
            <div className="btn-row">
              <button className="btn btn-ghost" onClick={() => setPhase("consent")}>
                Empezar otra sesión
              </button>
            </div>
          </div>
        </main>
      </div>
    );
  }

  if (phase === "consent" && examInfo) {
    return (
      <div className="student on-black glow">
        {bar()}
        <main className="student-main enter">
          <span className="eyebrow">Antes de empezar</span>
          <h1>{examInfo.name}</h1>
          <p className="lead">
            Mientras rendís, esta página registra cómo interactuás con ella. Leé qué se registra y, si estás de
            acuerdo, empezá. La consigna aparece después.
          </p>

          <section className="consent-block" aria-labelledby="que-se-registra">
            <h2 id="que-se-registra">Qué se registra</h2>
            {examInfo.allowed_signals.length === 0 ? (
              <p className="muted">En esta evaluación no se registra ninguna señal de interacción.</p>
            ) : (
              <ul className="signal-list" aria-label="Señales registradas">
                {examInfo.allowed_signals.map((s) => {
                  const Icon = SIGNAL_ICONS[s] ?? Keyboard;
                  const desc = SIGNAL_STUDENT_DESCRIPTIONS[s] ?? signalLabel(s);
                  const [title, ...rest] = desc.split(": ");
                  return (
                    <li key={s}>
                      <span className="sig-icon">
                        <Icon size={18} aria-hidden="true" />
                      </span>
                      <span>
                        <strong>{rest.length ? title : SIGNAL_SHORT[s] ?? title}</strong>
                        {rest.length ? capitalize(rest.join(": ")) : desc}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
            <div className="not-recorded">
              <ShieldCheck size={18} aria-hidden="true" />
              <span>
                No se registra qué teclas presionás ni el contenido que pegás. Tu docente ve tu respuesta final y estas
                métricas; ninguna decisión se toma de forma automática.
              </span>
            </div>
          </section>

          {examInfo.info_text && (
            <section className="consent-block" aria-labelledby="mensaje-docente">
              <h2 id="mensaje-docente">Mensaje de tu docente</h2>
              <p className="teacher-note">{examInfo.info_text}</p>
            </section>
          )}

          <section className="consent-block" aria-labelledby="reglas">
            <h2 id="reglas">Reglas y recursos permitidos</h2>
            <p className="rules-note">{examInfo.rules_text}</p>
          </section>

          <form className="start-form" onSubmit={handleStart} noValidate>
            {error && (
              <div className="alert alert-error" role="alert">
                <AlertCircle size={17} aria-hidden="true" />
                <span className="alert-body">{error}</span>
              </div>
            )}
            <label className="field">
              <span className="field-label">Código de participante</span>
              <input
                className="pid-input"
                value={participantId}
                onChange={(e) => setParticipantId(e.target.value)}
                placeholder="ej. P-017 (el código que te asignó tu docente)"
                autoComplete="off"
                spellCheck={false}
              />
              <span className="field-hint">Es un seudónimo: no ingreses tu nombre ni tu legajo.</span>
            </label>

            {simulation && (
              <label className="field">
                <span className="field-label">Condición de esta simulación</span>
                <select value={condition} onChange={(e) => setCondition(e.target.value)}>
                  <option value="">Elegí una condición…</option>
                  {SIMULATION_CONDITIONS.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </select>
                <span className="field-hint">
                  Solo para las simulaciones del equipo: se guarda con la sesión y el docente no la ve.
                </span>
              </label>
            )}

            <label className="checkbox-row">
              <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
              Confirmo que leí la información de arriba y presto mi consentimiento para iniciar la captura.
            </label>

            <button type="submit" className="btn btn-primary btn-large btn-block" disabled={starting}>
              {starting && <Loader2 size={16} className="spin" aria-hidden="true" />}
              {starting ? "Iniciando…" : "Comenzar"}
            </button>
          </form>
        </main>
      </div>
    );
  }

  if (phase === "active") {
    const offline = sync.failures > 0;
    const countWords = (t: string) => (t.trim() ? t.trim().split(/\s+/).length : 0);
    const words = items
      ? items.reduce((n, it) => n + countWords(answers[it.id] ?? ""), 0)
      : countWords(answer);
    const missing = items ? items.filter((it) => !(answers[it.id] ?? "").trim()).map((it) => it.id) : [];
    const syncStatus = (
      <p
        className={offline ? "alert alert-warning" : "sr-only"}
        data-testid="sync-status"
        role="status"
        aria-live="polite"
      >
        {!offline
          ? sync.pending > 0
            ? `sincronizando… (${sync.pending} lote(s) en cola)`
            : `sincronizado (${sync.sent} eventos enviados)`
          : `Estás sin conexión: ${sync.pending} lote(s) pendientes, reintentando en ${sync.retryInS} s. Podés seguir escribiendo: los registros se guardan en este navegador hasta reconectar.`}
      </p>
    );
    const resumedNote = resumed && (
      <div className="alert alert-success" role="status">
        <RotateCcw size={17} aria-hidden="true" />
        <span className="alert-body">Retomamos tu sesión en curso: tus respuestas se recuperaron y la captura continúa.</span>
      </div>
    );
    const itemFields =
      items &&
      items.map((it, i) => {
        const val = answers[it.id] ?? "";
        return (
          <section key={it.id} className="sheet-item" data-item-ref={it.id} aria-labelledby={`ej-${it.id}`}>
            <div className="sheet-item-head">
              <h2 id={`ej-${it.id}`}>Ejercicio {it.id}</h2>
              <span className={val.trim() ? "done" : ""}>
                {val.trim() ? <Check size={13} aria-hidden="true" /> : null}
                {countWords(val)} {countWords(val) === 1 ? "palabra" : "palabras"}
              </span>
            </div>
            {it.enunciado && <p className="sheet-item-prompt">{it.enunciado}</p>}
            <label>
              <span className="sr-only">Tu respuesta al ejercicio {it.id}</span>
              <textarea
                value={val}
                onChange={(e) => updateItemAnswer(it.id, e.target.value)}
                placeholder={tienePdf ? `Respuesta al ejercicio ${it.id} del enunciado…` : "Escribí tu respuesta acá…"}
                autoFocus={i === 0 && !resumed}
              />
            </label>
          </section>
        );
      });
    const footer = (
      <div className="sheet-foot">
        <span>
          {items ? `${items.length - missing.length} de ${items.length} ejercicios con respuesta · ` : ""}
          {words} {words === 1 ? "palabra" : "palabras"}
          {!items && ` · ${answer.length} caracteres`}
        </span>
        <span>Tus respuestas se guardan en esta pestaña mientras escribís: si se recarga, no se pierden.</span>
      </div>
    );

    return (
      <div className="student on-black">
        {bar(
          <>
            <span className={`sync-pill${offline ? " is-offline" : ""}`} aria-hidden="true">
              {offline ? <CloudOff size={14} /> : <span className="live-dot" />}
              <span className="sync-text">{offline ? "Sin conexión" : "Registrando"}</span>
            </span>
            <button className="btn btn-primary" onClick={() => setConfirmFinish(true)}>
              Finalizar y entregar
            </button>
          </>,
        )}
        {tienePdf && items ? (
          <main className="exam-split enter" ref={containerRef}>
            <section className="pdf-pane" aria-labelledby="enunciado-pdf">
              <h1 id="enunciado-pdf" className="sr-only">
                Enunciado del examen
              </h1>
              {pdfUrl ? (
                <iframe src={`${pdfUrl}#view=FitH`} title="Enunciado del examen (PDF)" />
              ) : pdfError ? (
                <div className="pdf-msg">
                  <AlertCircle size={20} aria-hidden="true" />
                  No se pudo cargar el enunciado. Recargá la página; tus respuestas no se pierden.
                </div>
              ) : (
                <div className="pdf-msg">
                  <Loader2 size={20} className="spin" aria-hidden="true" /> Cargando el enunciado…
                </div>
              )}
            </section>
            <div className="answers-pane">
              {resumedNote}
              {syncStatus}
              <article className="sheet">
                {itemFields}
                {footer}
              </article>
            </div>
          </main>
        ) : (
          <main className="sheet-wrap enter" ref={containerRef}>
            {resumedNote}
            {syncStatus}
            <article className="sheet">
              <div className="sheet-prompt">
                <h1>{items ? `Consignas · ${items.length} ejercicios` : "Consigna"}</h1>
                {!items && <p>{promptText}</p>}
              </div>
              {items ? (
                itemFields
              ) : (
                <label className="sheet-label">
                  <span className="sr-only">Tu respuesta</span>
                  <textarea
                    value={answer}
                    onChange={(e) => updateAnswer(e.target.value)}
                    placeholder="Escribí tu respuesta acá…"
                  />
                </label>
              )}
              {footer}
            </article>
          </main>
        )}
        <ConfirmDialog
          open={confirmFinish}
          dark
          title="¿Entregar ahora?"
          confirmLabel="Sí, entregar"
          cancelLabel="Seguir escribiendo"
          onConfirm={() => handleFinish()}
          onCancel={() => setConfirmFinish(false)}
        >
          <p>Después de entregar no vas a poder editar tus respuestas.</p>
          {missing.length > 0 ? (
            <p className="alert alert-warning" style={{ marginBottom: 12 }}>
              {missing.length === 1 ? `El ejercicio ${missing[0]} está` : `Los ejercicios ${missing.join(", ")} están`} sin
              respuesta.
            </p>
          ) : (
            <p>
              {items ? `Respondiste los ${items.length} ejercicios · ` : "Tu respuesta tiene "}
              {words} {words === 1 ? "palabra" : "palabras"}.
            </p>
          )}
        </ConfirmDialog>
      </div>
    );
  }

  if (phase === "finishing") {
    const messages: Record<FinishStep, string> = {
      sending: "Enviando los últimos registros…",
      closing: "Confirmando la entrega con el servidor…",
      error_sync: `No se pudieron enviar ${unsentAtFinish} registro(s) de interacción. Revisá la conexión y reintentá.`,
      error_close:
        "No se pudo confirmar la entrega con el servidor. Tu respuesta no se perdió: sigue en esta pestaña. Reintentá en unos segundos sin cerrarla.",
    };
    const failed = finishStep === "error_sync" || finishStep === "error_close";
    return (
      <div className="student on-black glow">
        {bar()}
        <main className="result" ref={containerRef}>
          <div className="result-inner enter">
            <span className={`mark-ok${failed ? " is-error" : ""}`}>
              {failed ? <CloudOff size={28} aria-hidden="true" /> : <Loader2 size={28} className="spin" aria-hidden="true" />}
            </span>
            <h1>{failed ? "La entrega no está confirmada" : "Entregando…"}</h1>
            <p
              className="muted"
              data-testid="finish-status"
              role={failed ? "alert" : "status"}
              aria-live={failed ? "assertive" : "polite"}
            >
              {messages[finishStep]}
            </p>
            {failed && (
              <div className="btn-row">
                <button className="btn btn-primary btn-large" onClick={() => handleFinish()}>
                  Reintentar la entrega
                </button>
                {finishStep === "error_sync" && (
                  <button className="btn btn-ghost btn-large" onClick={() => handleFinish(true)}>
                    Entregar sin esos registros
                  </button>
                )}
              </div>
            )}
          </div>
        </main>
      </div>
    );
  }

  // finished
  return (
    <div className="student on-black glow">
      {bar()}
      <main className="result" ref={containerRef}>
        <div className="result-inner enter" role="status">
          <span className="mark-ok">
            <Check size={30} aria-hidden="true" />
          </span>
          <h1>Entrega confirmada</h1>
          {unsentAtFinish === 0 ? (
            <p className="muted">El servidor confirmó tu entrega. Ya podés cerrar esta pestaña.</p>
          ) : (
            <p className="muted">
              El servidor confirmó tu entrega, pero {unsentAtFinish} registros de interacción no se pudieron enviar por
              problemas de conexión. Avisale a tu docente.
            </p>
          )}
        </div>
      </main>
    </div>
  );
}

function StudentStepper({ step }: { step: number }) {
  const steps = ["Código", "Información", "Respuesta", "Entrega"];
  return (
    <ol className="stepper" aria-label="Pasos">
      {steps.map((s, i) => {
        const n = i + 1;
        return (
          <li key={s} aria-current={n === step ? "step" : undefined} className={n < step ? "done" : ""}>
            <span className="n">{n < step ? <Check size={11} strokeWidth={3} aria-hidden="true" /> : n}</span>
            <span className="lbl">{s}</span>
          </li>
        );
      })}
    </ol>
  );
}

function capitalize(t: string): string {
  return t.charAt(0).toUpperCase() + t.slice(1);
}
