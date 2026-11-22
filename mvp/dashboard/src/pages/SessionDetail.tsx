import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AlertCircle, ArrowRight, ExternalLink, CheckCircle2, ChevronDown, ChevronRight, Info, Loader2, ShieldAlert, Trash2 } from "lucide-react";
import { api, type Indicator, type SessionDetail as SessionDetailT, type SessionSummary } from "../api";
import {
  INFORMATIVE_INDICATORS,
  MODEL_FEATURES_NOTE,
  MODEL_INDICATOR_NOTE,
  MODEL_STATE_LABELS,
  REVIEW_ACTION_LABELS,
  METRIC_LABELS,
  formatDateTime,
  formatMetricValue,
  indicatorLabel,
  metricName,
  sessionTypeLabel,
  sortSessionsForReview,
} from "../format";
import { usePageTitle } from "../a11y";
import { REVIEWS_CHANGED_EVENT } from "../Layout";
import { openExamPdf } from "../EnunciadoCard";
import { ConfirmDialog, Level, Loading, ReviewChip, indicatorIcon, shortWhen } from "../ui";

/**
 * Posición relativa de la sesión en la línea base, en palabras (Incremento 10).
 * Cap. 15: al docente no se le muestra el valor crudo del score ni una probabilidad,
 * sino una categoría relativa a la muestra y los factores que más contribuyeron.
 */
function populationBand(exp: Record<string, unknown>): string | null {
  const pct = exp.population_percentile;
  const n = exp.population_size;
  if (typeof pct !== "number" || typeof n !== "number" || n <= 0) return null;
  if (pct === 0) return `Resultó más atípica que las ${n} sesiones de esta evaluación usadas como línea base.`;
  const share = Math.ceil(pct * 100);
  return `Se ubica dentro del ${share} % más atípico de las ${n} sesiones de esta evaluación usadas como línea base.`;
}

const Z_RANGE = 4; // la escala va de −4 a +4 desvíos; lo que excede se dibuja en el borde

/** Desvíos de la sesión frente a la cohorte: banda = ±1 desvío, punto = esta sesión. */
function ZPlot({ features }: { features: { metric: string; value: number; population_mean: number; z_score: number }[] }) {
  const pos = (z: number) => ((Math.max(-Z_RANGE, Math.min(Z_RANGE, z)) + Z_RANGE) / (2 * Z_RANGE)) * 100;
  return (
    <>
      <ul className="zplot">
        {features.map((f) => {
          const clamped = Math.abs(f.z_score) > Z_RANGE;
          return (
            <li key={f.metric}>
              <span className="zname">{METRIC_LABELS[f.metric] || f.metric}</span>
              <span
                className="zscale"
                role="img"
                aria-label={`${Math.abs(f.z_score).toFixed(1)} desvíos ${f.z_score >= 0 ? "por encima" : "por debajo"} de la media de la cohorte`}
              >
                <span className="zband" style={{ left: `${pos(-1)}%`, width: `${pos(1) - pos(-1)}%` }} />
                <span className="zmid" style={{ left: `${pos(0)}%` }} />
                <span className={`zdot${clamped ? " clamped" : ""}`} style={{ left: `${pos(f.z_score)}%` }} />
              </span>
              <span className="zval">
                {f.value.toFixed(2)} vs {f.population_mean.toFixed(2)}
                <br />
                {f.z_score >= 0 ? "+" : "−"}
                {Math.abs(f.z_score).toFixed(1)} desvíos
              </span>
            </li>
          );
        })}
      </ul>
      <div className="zlegend" aria-hidden="true">
        <span>
          <i className="sw-band" /> rango habitual de la cohorte (±1 desvío)
        </span>
        <span>
          <i className="sw-dot" /> esta sesión
        </span>
      </div>
    </>
  );
}

/** Como formatMetricValue, pero los tiempos cortos se muestran en ms (0,0 s no dice nada). */
function fmtEvidence(metric: string, v: number): string {
  if (metric.endsWith("_ms") && Math.abs(v) < 1000) return `${Math.round(v).toLocaleString("es-AR")} ms`;
  return formatMetricValue(metric, v);
}

/** Valor de la métrica frente a su umbral de referencia. */
function Meter({ metric, value, threshold }: { metric: string; value: number; threshold: number }) {
  const max = Math.max(value, threshold) * 1.25 || 1;
  const pct = (v: number) => `${Math.min(100, (v / max) * 100).toFixed(1)}%`;
  const ratio = threshold > 0 ? value / threshold : null;
  return (
    <div className="meter">
      <div className="meter-figure">
        {fmtEvidence(metric, value)}
        <small>
          {metricName(metric)}
          {ratio && ratio >= 1.1 ? ` · ${ratio.toFixed(1).replace(".", ",")}× el umbral` : ""}
        </small>
      </div>
      <div
        className="meter-track"
        role="img"
        aria-label={`${metricName(metric)}: ${fmtEvidence(metric, value)}; umbral de referencia ${fmtEvidence(metric, threshold)}`}
      >
        <span className="meter-fill" style={{ width: pct(value) }} />
        <span className="meter-threshold" style={{ left: pct(threshold) }}>
          <span>{fmtEvidence(metric, threshold)}</span>
        </span>
      </div>
    </div>
  );
}

function IndicatorEvidence({ indicator }: { indicator: Indicator }) {
  const exp = indicator.explanation;
  if (exp.model === "isolation_forest_poblacional") {
    const top = (exp.top_features as { metric: string; value: number; population_mean: number; z_score: number }[]) || [];
    const band = populationBand(exp);
    return (
      <div className="indicator-evidence">
        <p>
          <strong>{MODEL_INDICATOR_NOTE}</strong> {band}
        </p>
        <p className="evidence-note" style={{ marginBottom: 6 }}>
          {MODEL_FEATURES_NOTE}
        </p>
        <ZPlot features={top} />
        <p className="evidence-note">Modelo: análisis de la cohorte de la evaluación al cerrarla (Isolation Forest).</p>
      </div>
    );
  }
  if (indicator.kind === "captura_incompleta") {
    return (
      <div className="indicator-evidence">
        Eventos descartados: <strong>{String(exp.capture_dropped_events ?? 0)}</strong> · interrupciones prolongadas de
        la sincronización: <strong>{String(exp.sync_failure_count ?? 0)}</strong>. Este aviso no prioriza la sesión para
        revisión.
      </div>
    );
  }
  const metric = String(exp.metric ?? "");
  const value = typeof exp.value === "number" ? exp.value : null;
  const threshold = typeof exp.threshold === "number" ? exp.threshold : null;
  return (
    <div className="indicator-evidence">
      {value !== null && threshold !== null ? (
        <Meter metric={metric} value={value} threshold={threshold} />
      ) : (
        <p>
          {metricName(metric)}: <strong>{formatMetricValue(metric, exp.value)}</strong> · umbral de referencia:{" "}
          {formatMetricValue(metric, exp.threshold)}
        </p>
      )}
      {Boolean(exp.permitido_por_reglas) && (
        <p className="evidence-note">Permitido por las reglas de esta evaluación: se registra, pero no prioriza la sesión.</p>
      )}
    </div>
  );
}

export default function SessionDetail() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [session, setSession] = useState<SessionDetailT | null>(null);
  const [siblings, setSiblings] = useState<SessionSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [selectedIndicators, setSelectedIndicators] = useState<string[]>([]);
  const [reviewMsg, setReviewMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const navigate = useNavigate();
  usePageTitle(session ? `Sesión de ${session.participant_id}` : error ? "Sesión no disponible" : "Sesión");

  // Problema 5: después de eliminar se vuelve a las sesiones de la evaluación, con un aviso.
  async function deleteSession() {
    if (!sessionId || !session) return;
    setDeleteError(null);
    try {
      await api.deleteSession(sessionId);
      navigate(`/exams/${session.exam_id}/sessions`, {
        replace: true,
        state: { msg: `Sesión de ${session.participant_id} eliminada, con todos sus datos.` },
      });
    } catch {
      setDeleteError("No se pudo eliminar la sesión. Reintentá en unos segundos.");
      setConfirmDelete(false);
    }
  }

  function load() {
    if (!sessionId) return;
    api.getSession(sessionId).then(setSession).catch(() => setError("No se pudo cargar la sesión."));
  }

  useEffect(() => {
    setSession(null);
    setReviewMsg(null);
    setNotes("");
    setSelectedIndicators([]);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  // Sesiones de la misma evaluación, para ofrecer «siguiente para revisar».
  const examId = session?.exam_id;
  useEffect(() => {
    if (!examId) return;
    api.listSessions({ exam_id: examId }).then(setSiblings).catch(() => setSiblings([]));
  }, [examId, reviewMsg]);

  function toggleIndicator(id: string) {
    setSelectedIndicators((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  async function submitReview(action: "marked_reviewed" | "additional_validation") {
    if (!sessionId) return;
    setReviewMsg(null);
    setSaving(action);
    try {
      await api.createReview(sessionId, action, notes || null, selectedIndicators);
      setReviewMsg({
        ok: true,
        text:
          action === "marked_reviewed"
            ? "Se dejó constancia de que revisaste esta sesión."
            : "Se marcó que esta sesión requiere validación adicional.",
      });
      setNotes("");
      setSelectedIndicators([]);
      load(); // refresca historial y estado de revisión
      window.dispatchEvent(new Event(REVIEWS_CHANGED_EVENT)); // contador de la barra (problema 13)
    } catch {
      setReviewMsg({ ok: false, text: "No se pudo registrar la revisión." });
    } finally {
      setSaving(null);
    }
  }

  if (error)
    return (
      <div className="page page-narrow">
        <h1>Sesión no disponible</h1>
        <div className="alert alert-error" role="alert" style={{ marginTop: 16 }}>
          <AlertCircle size={17} aria-hidden="true" />
          <span className="alert-body">{error}</span>
        </div>
        <Link className="btn btn-ghost" to="/exams">
          Volver a Evaluaciones
        </Link>
      </div>
    );
  if (!session)
    return (
      <div className="page">
        <Loading />
      </div>
    );

  const metricsByItem = new Map<string | null, typeof session.metrics>();
  for (const m of session.metrics) {
    const key = m.item_ref ?? null;
    metricsByItem.set(key, [...(metricsByItem.get(key) || []), m]);
  }
  const itemGroups = [...metricsByItem.entries()].sort(([a], [b]) => (a === null ? -1 : b === null ? 1 : a.localeCompare(b)));

  const queue = sortSessionsForReview(siblings).filter(
    (s) => s.id !== session.id && s.needs_review && s.review_status === "sin_revision",
  );
  const next = queue[0];
  const durationMs = session.ended_at ? Date.parse(session.ended_at) - Date.parse(session.started_at) : null;
  const sortedIndicators = [...session.indicators].sort((a, b) => {
    const rank = (i: Indicator) =>
      INFORMATIVE_INDICATORS.includes(i.kind) || i.explanation.permitido_por_reglas ? 2 : i.kind === "atipico_modelo_poblacional" ? 1 : 0;
    return rank(a) - rank(b);
  });

  return (
    <div className="page">
      <nav className="crumbs" aria-label="Ruta">
        <Link to="/exams">Evaluaciones</Link>
        <ChevronRight size={14} aria-hidden="true" />
        <Link to={`/exams/${session.exam_id}/sessions`}>{session.exam_name || "Evaluación"}</Link>
        <ChevronRight size={14} aria-hidden="true" />
        <span aria-current="page">{session.participant_id}</span>
      </nav>

      <div className="page-head">
        <div>
          <h1>
            Sesión de <span className="mono" style={{ fontSize: "0.9em", fontWeight: 500 }}>{session.participant_id}</span>
          </h1>
          <p className="sub">
            {session.needs_review ? (
              <span className="chip chip-warn">
                <ShieldAlert size={13} aria-hidden="true" /> Requiere revisión
              </span>
            ) : session.indicators.length > 0 ? (
              <span className="chip chip-info">Solo avisos informativos</span>
            ) : (
              <span className="chip">Sin indicadores</span>
            )}
            <span>
              {sessionTypeLabel(session.session_type)} · {session.status === "active" ? "en curso" : "finalizada"} ·{" "}
              {formatDateTime(session.started_at)}
              {durationMs !== null && durationMs > 0 && ` · ${formatMetricValue("session_wall_duration_ms", durationMs)}`}
            </span>
          </p>
        </div>
      </div>

      <div className="detail-grid">
        <div>
          <div className="disclaimer">
            <Info size={17} aria-hidden="true" />
            <span>
              Los indicadores señalan que una métrica superó un umbral o que el proceso se apartó del de la cohorte. No
              son una conclusión sobre fraude: la decisión es siempre del docente.
            </span>
          </div>

          {session.indicators.length === 0 ? (
            <div className="card">
              <h3>Indicadores preliminares</h3>
              <p className="muted">No se generaron indicadores para esta sesión.</p>
            </div>
          ) : (
            <>
              <h2 className="sr-only">Indicadores preliminares</h2>
              <ul className="indicator-list stagger">
                {sortedIndicators.map((ind, i) => {
                  const informative = INFORMATIVE_INDICATORS.includes(ind.kind) || Boolean(ind.explanation.permitido_por_reglas);
                  const Icon = indicatorIcon(ind.kind);
                  const cls =
                    ind.kind === "atipico_modelo_poblacional"
                      ? " indicator-model"
                      : informative
                        ? " indicator-info"
                        : "";
                  return (
                    <li key={ind.id} className={`indicator-item${cls}`} style={{ ["--i" as string]: i }}>
                      <span className="ind-icon">
                        <Icon size={18} aria-hidden="true" />
                      </span>
                      <div>
                        <div className="indicator-top">
                          <div>
                            <span className="indicator-kind">{indicatorLabel(ind.kind)}</span>
                            <Level level={ind.level} />
                          </div>
                          <label className="checkbox-row indicator-cite">
                            <input
                              type="checkbox"
                              checked={selectedIndicators.includes(ind.id)}
                              onChange={() => toggleIndicator(ind.id)}
                            />
                            Citar en la revisión
                          </label>
                        </div>
                        <p className="indicator-desc">{ind.description}</p>
                      </div>
                      <IndicatorEvidence indicator={ind} />
                    </li>
                  );
                })}
              </ul>
            </>
          )}

          <section className="card" aria-labelledby="resp">
            <div className="card-head">
              <h3 id="resp">{session.items ? "Respuestas entregadas" : "Respuesta entregada"}</h3>
              <div className="btn-row">
                {session.respuesta && (
                  <span className="muted small">{session.respuesta.trim().split(/\s+/).length} palabras</span>
                )}
                {session.tiene_pdf && (
                  <button className="btn btn-ghost btn-small" onClick={() => openExamPdf(session.exam_id)}>
                    <ExternalLink size={14} aria-hidden="true" />
                    Ver enunciado (PDF)
                  </button>
                )}
              </div>
            </div>
            {session.items && session.respuestas ? (
              session.items.map((it) => {
                const r = session.respuestas?.[it.id]?.trim();
                return (
                  <div key={it.id} className="answer-item">
                    <h4>Ejercicio {it.id}</h4>
                    {it.enunciado && <p className="enunciado">{it.enunciado}</p>}
                    {r ? <p className="answer-sheet">{r}</p> : <p className="muted small">Sin respuesta.</p>}
                  </div>
                );
              })
            ) : session.respuesta ? (
              <p className="answer-sheet">{session.respuesta}</p>
            ) : (
              <p className="muted">El estudiante no entregó una respuesta escrita en esta sesión.</p>
            )}
          </section>

          <section className="card" aria-labelledby="ctx">
            <h3 id="ctx">Contexto de la sesión</h3>
            <dl className="facts">
              <div>
                <dt>Eventos registrados</dt>
                <dd>{session.event_count.toLocaleString("es-AR")}</dd>
              </div>
              <div>
                <dt>Análisis poblacional</dt>
                <dd>{MODEL_STATE_LABELS[session.estado_modelo]?.split(" (")[0] ?? session.estado_modelo}</dd>
              </div>
              <div>
                <dt>Inicio</dt>
                <dd>{formatDateTime(session.started_at)}</dd>
              </div>
              <div>
                <dt>Entrega</dt>
                <dd>{session.ended_at ? formatDateTime(session.ended_at) : "En curso"}</dd>
              </div>
              {Object.entries(session.context).map(([k, v]) => (
                <div key={k}>
                  <dt>{k}</dt>
                  <dd>{String(v)}</dd>
                </div>
              ))}
            </dl>
            {MODEL_STATE_LABELS[session.estado_modelo]?.includes("(") && (
              <p className="muted small" style={{ marginTop: 10 }}>
                Análisis poblacional: {MODEL_STATE_LABELS[session.estado_modelo]}.
              </p>
            )}
            {!session.procesada && session.status !== "active" && (
              <div className="alert alert-error" style={{ marginTop: 12, marginBottom: 0 }}>
                El procesamiento de esta sesión no terminó: se reintenta cuando el estudiante repite el cierre o al cerrar
                la evaluación.
              </div>
            )}
          </section>

          <details className="disclosure">
            <summary>
              <h3>Todas las métricas calculadas</h3>
              <ChevronDown size={18} aria-hidden="true" />
            </summary>
            <div className="disclosure-body">
              {itemGroups.map(([itemRef, metrics]) => (
                <div key={itemRef ?? "__global__"} style={{ marginBottom: 12 }}>
                  <div className="metric-group-label">{itemRef ? `Ejercicio ${itemRef}` : "Sesión completa"}</div>
                  <dl className="metric-grid">
                    {metrics.map((m) => (
                      <div key={m.id}>
                        <dt>{METRIC_LABELS[m.name] || m.name}</dt>
                        <dd>{Number.isInteger(m.value) ? m.value.toLocaleString("es-AR") : m.value.toFixed(2)}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              ))}
            </div>
          </details>

          {deleteError && (
            <div className="alert alert-error" role="alert">
              {deleteError}
            </div>
          )}
          <button className="btn btn-danger-quiet btn-small" onClick={() => setConfirmDelete(true)}>
            <Trash2 size={14} aria-hidden="true" />
            Eliminar esta sesión…
          </button>
        </div>

        <aside className="review-panel" aria-label="Revisión docente">
          <section className="card" id="revision" aria-labelledby="rev-title">
            <div className="review-status">
              <h3 id="rev-title">Revisión docente</h3>
              <ReviewChip status={session.review_status} />
            </div>
            <label className="field">
              <span className="field-label">Notas (opcional)</span>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Qué miraste y qué concluiste…"
              />
              {selectedIndicators.length > 0 && (
                <span className="field-hint">
                  Citando {selectedIndicators.length} {selectedIndicators.length === 1 ? "indicador" : "indicadores"}.
                </span>
              )}
            </label>
            <div className="review-actions">
              <button className="btn btn-primary" onClick={() => submitReview("marked_reviewed")} disabled={saving !== null}>
                {saving === "marked_reviewed" ? (
                  <Loader2 size={15} className="spin" aria-hidden="true" />
                ) : (
                  <CheckCircle2 size={15} aria-hidden="true" />
                )}
                Marcar como revisada
              </button>
              <button
                className="btn btn-warning"
                onClick={() => submitReview("additional_validation")}
                disabled={saving !== null}
              >
                {saving === "additional_validation" && <Loader2 size={15} className="spin" aria-hidden="true" />}
                Requiere validación adicional
              </button>
            </div>
            <p className="muted small" style={{ marginTop: 10 }}>
              Pedí validación adicional si la evidencia no alcanza (por ejemplo, para una instancia oral).
            </p>
            <div role="status" aria-live="polite">
              {reviewMsg && (
                <div className={`alert ${reviewMsg.ok ? "alert-success" : "alert-error"}`} style={{ marginTop: 14, marginBottom: 0 }}>
                  {reviewMsg.text}
                </div>
              )}
            </div>

            {session.reviews.length > 0 && (
              <ol className="timeline" aria-label="Historial de revisión">
                <li style={{ display: "block" }}>
                  <span className="timeline-title">Historial · no se edita ni se borra</span>
                </li>
                {[...session.reviews].reverse().map((r) => (
                  <li key={r.id} className={r.action === "additional_validation" ? "pending" : ""}>
                    <span className="dot" aria-hidden="true" />
                    <div>
                      <strong>{REVIEW_ACTION_LABELS[r.action] ?? r.action}</strong>
                      <div className="when">
                        {shortWhen(r.created_at)}
                        {r.teacher_email && ` · ${r.teacher_email}`}
                        {r.indicator_ids.length > 0 && ` · ${r.indicator_ids.length} indicador(es)`}
                      </div>
                      {r.notes && <div className="note">{r.notes}</div>}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>

          {next ? (
            <Link className="next-link" to={`/sessions/${next.id}`}>
              <span>
                <small>
                  Siguiente para revisar · quedan {queue.length}
                </small>
                <span className="pid">{next.participant_id}</span>
              </span>
              <ArrowRight size={18} aria-hidden="true" />
            </Link>
          ) : (
            siblings.length > 0 && (
              <Link className="btn btn-ghost btn-block" to={`/exams/${session.exam_id}/sessions`}>
                Volver a las entregas
              </Link>
            )
          )}
        </aside>
      </div>

      <ConfirmDialog
        open={confirmDelete}
        tone="danger"
        title="¿Eliminar esta sesión?"
        confirmLabel="Confirmar la eliminación"
        onConfirm={deleteSession}
        onCancel={() => setConfirmDelete(false)}
      >
        <p>
          Se borran la respuesta, los eventos, las métricas, los indicadores y las revisiones de {session.participant_id},
          por ejemplo a pedido del estudiante. No se puede deshacer.
        </p>
      </ConfirmDialog>
    </div>
  );
}
