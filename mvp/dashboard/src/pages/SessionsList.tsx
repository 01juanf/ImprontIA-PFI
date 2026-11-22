import { useEffect, useMemo, useState, type KeyboardEvent } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { AlertCircle, ArrowRight, CheckCircle2, ChevronRight, Fingerprint, Inbox, Lock, Trash2, X } from "lucide-react";
import { ApiError, api, type Exam, type Panorama, type SessionSummary } from "../api";
import { MODEL_STATE_SHORT, formatDateTime, sortSessionsForReview } from "../format";
import { usePageTitle } from "../a11y";
import PolicyCard from "../PolicyCard";
import EnunciadoCard from "../EnunciadoCard";
import PanoramaView from "../PanoramaView";
import CopyLinkButton from "../CopyLinkButton";
import { ConfirmDialog, EmptySimple, ExamStateChip, ReviewChip, SkeletonRows, Trace, TraceLegend, shortWhen } from "../ui";

type Tab = "sesiones" | "panorama" | "config";
const TABS: { id: Tab; label: string }[] = [
  { id: "sesiones", label: "Entregas" },
  { id: "panorama", label: "Panorama" },
  { id: "config", label: "Configuración" },
];
const MIN_COHORT = 20; // backend: el modelo poblacional necesita al menos 20 sesiones finalizadas

export default function SessionsList() {
  const { examId } = useParams<{ examId: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  // Problema 6: el filtro y la pestaña viven en la URL (?revision=1&tab=panorama).
  const [params, setParams] = useSearchParams();
  const onlyNeedsReview = params.get("revision") === "1";
  const tabParam = params.get("tab");
  const tab: Tab = tabParam === "panorama" ? "panorama" : tabParam === "config" ? "config" : "sesiones";

  const [exam, setExam] = useState<Exam | null>(null);
  const [examError, setExamError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  const [confirmClose, setConfirmClose] = useState(false);
  const [closing, setClosing] = useState(false);
  const [closeError, setCloseError] = useState<string | null>(null);
  const [justClosed, setJustClosed] = useState(false);
  const [closeSummary, setCloseSummary] = useState<Panorama | null>(null);
  const navState = location.state as { msg?: string; created?: boolean } | null;
  const [flash, setFlash] = useState<string | null>(navState?.msg ?? null);
  const [created] = useState<boolean>(Boolean(navState?.created));
  const [confirmDeleteExam, setConfirmDeleteExam] = useState(false);
  const [deletingExam, setDeletingExam] = useState(false);
  const [deleteExamError, setDeleteExamError] = useState<string | null>(null);

  usePageTitle(exam ? `Sesiones: ${exam.name}` : "Sesiones");

  useEffect(() => {
    // El aviso se muestra una vez: se limpia del historial para que no reaparezca al recargar.
    if (navState?.msg || navState?.created) navigate(location.pathname + location.search, { replace: true, state: null });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function updateParams(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v === null) next.delete(k);
      else next.set(k, v);
    }
    setParams(next); // push: cada cambio de pestaña o filtro queda en el historial
  }

  function loadExam() {
    if (!examId) return;
    api
      .getExam(examId)
      .then((e) => {
        setExam(e);
        setExamError(null);
      })
      .catch((err) =>
        setExamError(
          err instanceof ApiError && err.status === 404
            ? "No se encontró esta evaluación. Puede que se haya eliminado o que el enlace sea incorrecto."
            : "No se pudo cargar la evaluación.",
        ),
      );
  }

  useEffect(loadExam, [examId]);

  // Se cargan todas las entregas: el filtro «para revisar» se aplica acá, así los totales no cambian.
  useEffect(() => {
    if (!examId) return;
    setLoading(true);
    api
      .listSessions({ exam_id: examId })
      .then(setSessions)
      .catch(() => setSessions([]))
      .finally(() => setLoading(false));
  }, [examId, refresh]);

  useEffect(() => {
    if (!examId || !exam?.cerrada_at) return;
    api.getPanorama(examId).then(setCloseSummary).catch(() => setCloseSummary(null));
  }, [examId, exam?.cerrada_at, refresh]);

  const counts = useMemo(() => {
    const finished = sessions.filter((s) => s.status !== "active").length;
    return {
      total: sessions.length,
      active: sessions.length - finished,
      finished,
      needsReview: sessions.filter((s) => s.needs_review).length,
      toReview: sessions.filter((s) => s.needs_review && s.review_status === "sin_revision").length,
      reviewed: sessions.filter((s) => s.review_status === "revisada").length,
      validation: sessions.filter((s) => s.review_status === "validacion_pendiente").length,
    };
  }, [sessions]);

  // Primero lo que falta revisar; las ya revisadas bajan aunque tengan indicadores.
  const rank = (s: SessionSummary) =>
    s.needs_review && s.review_status === "sin_revision"
      ? 0
      : s.review_status === "validacion_pendiente"
        ? 1
        : s.needs_review
          ? 2
          : 3;
  const visible = sortSessionsForReview(onlyNeedsReview ? sessions.filter((s) => s.needs_review) : sessions)
    .map((s, i) => ({ s, i }))
    .sort((a, b) => rank(a.s) - rank(b.s) || a.i - b.i)
    .map(({ s }) => s);

  // Atajo de la vista general: la primera entrega que falta revisar, en el orden de la lista.
  const firstPending = sortSessionsForReview(sessions).find((s) => s.needs_review && s.review_status === "sin_revision");

  // Incremento 16: el análisis poblacional se hace una vez, al cerrar, sobre todas las sesiones.
  async function closeExam() {
    if (!examId) return;
    setClosing(true);
    setCloseError(null);
    try {
      setExam(await api.closeExam(examId));
      setJustClosed(true);
      setRefresh((n) => n + 1);
    } catch {
      setCloseError("No se pudo cerrar la evaluación. Reintentá en unos segundos.");
    } finally {
      setClosing(false);
      setConfirmClose(false);
    }
  }

  function onTabsKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const order = TABS.map((t) => t.id);
    const focusedId = (e.target as HTMLElement).id.replace("tab-", "") as Tab;
    const i = Math.max(0, order.indexOf(order.includes(focusedId) ? focusedId : tab));
    let next: Tab | null = null;
    if (e.key === "ArrowRight") next = order[(i + 1) % order.length];
    else if (e.key === "ArrowLeft") next = order[(i - 1 + order.length) % order.length];
    else if (e.key === "Home") next = order[0];
    else if (e.key === "End") next = order[order.length - 1];
    if (!next) return;
    e.preventDefault();
    if (next !== tab) updateParams({ tab: next === "sesiones" ? null : next });
    document.getElementById(`tab-${next}`)?.focus();
  }

  async function deleteExam() {
    if (!examId || !exam) return;
    setDeletingExam(true);
    setDeleteExamError(null);
    try {
      await api.deleteExam(examId);
      navigate("/exams", {
        replace: true,
        state: { msg: `Evaluación «${exam.name}» eliminada, con todas sus sesiones y datos.` },
      });
    } catch {
      setDeleteExamError("No se pudo eliminar la evaluación. Reintentá en unos segundos.");
      setDeletingExam(false);
      setConfirmDeleteExam(false);
    }
  }

  if (examError) {
    return (
      <div className="page page-narrow">
        <h1>Evaluación no encontrada</h1>
        <div className="alert alert-error" role="alert" style={{ marginTop: 16 }}>
          <AlertCircle size={17} aria-hidden="true" />
          <span className="alert-body">{examError}</span>
        </div>
        <Link className="btn btn-ghost" to="/exams">
          Volver a Evaluaciones
        </Link>
      </div>
    );
  }

  const cobertura = closeSummary?.cobertura;
  const closed = Boolean(exam?.cerrada_at);

  return (
    <div className="page">
      <nav className="crumbs" aria-label="Ruta">
        <Link to="/exams">Evaluaciones</Link>
        <ChevronRight size={14} aria-hidden="true" />
        <span aria-current="page">{exam?.name ?? "…"}</span>
      </nav>

      {!exam ? (
        <>
          <div className="skeleton" style={{ height: 40, width: "45%", marginBottom: 24 }} />
          <SkeletonRows rows={1} height={110} />
        </>
      ) : (
        <>
          <div className="page-head">
            <div>
              <h1>{exam.name}</h1>
              <p className="sub">
                <ExamStateChip closed={closed} />
                <span>
                  {closed ? `Cerrada ${shortWhen(exam.cerrada_at!)}` : `Creada ${shortWhen(exam.created_at)}`}
                </span>
                <span aria-hidden="true">·</span>
                <span>Política v{exam.policy_version}</span>
              </p>
            </div>
            {!created && !closed && (
              <div className="share-box">
                <div>
                  <div className="lbl">Código para estudiantes</div>
                  <div className="code join-code-raw">{exam.join_code}</div>
                </div>
                <CopyLinkButton joinCode={exam.join_code} examName={exam.name} dark />
              </div>
            )}
          </div>

          {created && (
            <section className="created on-black glow enter" aria-labelledby="creada-titulo">
              <div>
                <span className="eyebrow">Evaluación creada</span>
                <h2 id="creada-titulo">Compartí este código con tus estudiantes</h2>
                <p className="muted">
                  Lo ingresan en la página de inicio, o abren directamente el enlace. Las entregas van a aparecer acá.
                </p>
              </div>
              <div className="created-right">
                <div className="code-big join-code-raw">{exam.join_code}</div>
                <CopyLinkButton joinCode={exam.join_code} examName={exam.name} dark />
              </div>
            </section>
          )}

          {flash && (
            <div className="alert alert-success" role="status">
              <CheckCircle2 size={17} aria-hidden="true" />
              <span className="alert-body">{flash}</span>
              <button className="btn btn-quiet btn-small btn-icon dismiss" onClick={() => setFlash(null)} aria-label="Ocultar este aviso">
                <X size={15} aria-hidden="true" />
              </button>
            </div>
          )}

          {closeError && (
            <div className="alert alert-error" role="alert">
              <AlertCircle size={17} aria-hidden="true" />
              <span className="alert-body">{closeError}</span>
            </div>
          )}

          {justClosed && closeSummary && (
            <div className="alert alert-success" role="status" data-testid="close-summary">
              <CheckCircle2 size={17} aria-hidden="true" />
              <span className="alert-body">
                Evaluación cerrada.{" "}
                {cobertura && cobertura.sesiones_evaluadas === 0
                  ? `El modelo no evaluó ninguna sesión (hacen falta al menos ${MIN_COHORT} entregas finalizadas).`
                  : `El modelo marcó ${closeSummary.modelo.sesiones_marcadas} de ${cobertura?.sesiones_evaluadas ?? closeSummary.n_sesiones} sesiones evaluadas.`}
              </span>
            </div>
          )}

          <div className="stats" aria-label="Resumen de la evaluación">
            <div className="stat-cell">
              <div className="lbl">Entregas</div>
              <div className="val">{loading ? "–" : counts.finished}</div>
              <div className="foot">{counts.active > 0 ? `${counts.active} en curso ahora` : "finalizadas"}</div>
            </div>
            <div className={`stat-cell${counts.toReview > 0 ? " is-warn" : ""}`}>
              <div className="lbl">Para revisar</div>
              <div className="val">{loading ? "–" : counts.toReview}</div>
              {firstPending ? (
                <Link className="stat-link" to={`/sessions/${firstPending.id}`}>
                  Empezar por {firstPending.participant_id}
                  <ArrowRight size={13} aria-hidden="true" />
                </Link>
              ) : (
                <div className="foot">{counts.total ? "nada pendiente" : "con indicadores, sin revisión"}</div>
              )}
            </div>
            <div className="stat-cell">
              <div className="lbl">Revisadas</div>
              <div className="val">
                {loading ? "–" : counts.reviewed}
                {counts.validation > 0 && <small>+{counts.validation} en validación</small>}
              </div>
              <div className="foot">con constancia docente</div>
            </div>
            <div className="stat-cell is-model">
              <div className="lbl">
                <Fingerprint size={14} aria-hidden="true" /> Modelo poblacional
              </div>
              {closed ? (
                closeSummary && cobertura && cobertura.sesiones_evaluadas > 0 ? (
                  <>
                    <div className="val">
                      {closeSummary.modelo.sesiones_marcadas}
                      <small>de {cobertura.sesiones_evaluadas}</small>
                    </div>
                    <div className="foot">sesiones con proceso distinto a la cohorte</div>
                  </>
                ) : (
                  <div className="model-wait">{closeSummary ? `No se ejecutó: menos de ${MIN_COHORT} entregas.` : "…"}</div>
                )
              ) : (
                <>
                  <div className="model-wait">Se ejecuta al cerrar la evaluación</div>
                  <button className="btn btn-primary btn-small" onClick={() => setConfirmClose(true)}>
                    <Lock size={14} aria-hidden="true" />
                    Cerrar y analizar
                  </button>
                </>
              )}
            </div>
          </div>

          <div className="tabs" role="tablist" aria-label="Vista de la evaluación" onKeyDown={onTabsKeyDown}>
            {TABS.map((t) => (
              <button
                key={t.id}
                role="tab"
                id={`tab-${t.id}`}
                aria-controls="panel-evaluacion"
                aria-selected={tab === t.id}
                tabIndex={tab === t.id ? 0 : -1}
                className={`tab${tab === t.id ? " tab-active" : ""}`}
                onClick={() => updateParams({ tab: t.id === "sesiones" ? null : t.id })}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div id="panel-evaluacion" role="tabpanel" aria-labelledby={`tab-${tab}`}>
            {tab === "panorama" && examId ? (
              <PanoramaView key={refresh} examId={examId} />
            ) : tab === "config" ? (
              <div className="enter">
                <EnunciadoCard exam={exam} onUpdated={loadExam} />
                <PolicyCard exam={exam} onUpdated={loadExam} />
                {deleteExamError && (
                  <div className="alert alert-error" role="alert">
                    {deleteExamError}
                  </div>
                )}
                <div className="danger-zone">
                  <div>
                    <h3>Eliminar la evaluación</h3>
                    <p>
                      Borra la evaluación, sus versiones de política y todas sus sesiones, con las respuestas, eventos,
                      métricas, indicadores y revisiones. No se puede deshacer.
                    </p>
                  </div>
                  <button className="btn btn-ghost" onClick={() => setConfirmDeleteExam(true)}>
                    <Trash2 size={15} aria-hidden="true" />
                    Eliminar esta evaluación…
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div className="toolbar">
                  <div className="segmented" role="group" aria-label="Filtrar entregas">
                    <button aria-pressed={!onlyNeedsReview} onClick={() => updateParams({ revision: null })}>
                      Todas <span className="n">{counts.total}</span>
                    </button>
                    <button aria-pressed={onlyNeedsReview} onClick={() => updateParams({ revision: "1" })}>
                      Requieren revisión <span className="n">{counts.needsReview}</span>
                    </button>
                  </div>
                  <TraceLegend />
                </div>
                {loading ? (
                  <SkeletonRows rows={6} height={50} />
                ) : visible.length === 0 ? (
                  onlyNeedsReview ? (
                    <EmptySimple icon={CheckCircle2} title="Ninguna entrega requiere revisión">
                      No se dispararon indicadores en esta evaluación.
                    </EmptySimple>
                  ) : (
                    <EmptySimple icon={Inbox} title="Todavía no hay entregas">
                      Compartí el código <span className="join-code">{exam.join_code}</span> y las entregas van a
                      aparecer acá a medida que lleguen.
                    </EmptySimple>
                  )
                ) : (
                  <div className="table-wrap">
                    <table className="table session-table">
                      <thead>
                        <tr>
                          <th>Participante</th>
                          <th>Indicadores</th>
                          <th>Revisión docente</th>
                          <th className="hide-sm">Modelo</th>
                          <th className="hide-sm">Inicio</th>
                          <th>
                            <span className="sr-only">Abrir</span>
                          </th>
                        </tr>
                      </thead>
                      <tbody className="stagger">
                        {visible.map((s, i) => (
                          <tr key={s.id} className={s.needs_review ? "row-flagged" : ""} style={{ ["--i" as string]: i }}>
                            <td className="nowrap">
                              <Link
                                className="pid"
                                to={`/sessions/${s.id}`}
                                aria-label={`Ver detalle de ${s.participant_id}`}
                              >
                                {s.participant_id}
                              </Link>
                              {s.status === "active" && (
                                <span className="chip chip-live" style={{ marginLeft: 8 }}>
                                  <span className="live-dot" aria-hidden="true" /> En curso
                                </span>
                              )}
                            </td>
                            <td>
                              <Trace session={s} />
                            </td>
                            <td>
                              <ReviewChip status={s.review_status} />
                            </td>
                            <td className="hide-sm muted small">{MODEL_STATE_SHORT[s.estado_modelo] ?? s.estado_modelo}</td>
                            <td className="hide-sm when" title={formatDateTime(s.started_at)}>
                              {shortWhen(s.started_at)}
                            </td>
                            <td className="go">
                              <ChevronRight size={18} aria-hidden="true" />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </div>

          <ConfirmDialog
            open={confirmClose}
            title="¿Cerrar la evaluación y analizar?"
            confirmLabel={closing ? "Analizando…" : "Confirmar el cierre"}
            busy={closing}
            onConfirm={closeExam}
            onCancel={() => setConfirmClose(false)}
          >
            <p>
              El modelo compara el proceso de cada entrega con el resto de la cohorte. Se ejecuta una sola vez, ahora.
              Después del cierre no se admiten entregas nuevas.
            </p>
            {counts.finished < MIN_COHORT && (
              <p className="alert alert-warning" style={{ marginBottom: 12 }}>
                Hay {counts.finished} entregas finalizadas: el modelo necesita al menos {MIN_COHORT}. Si cerrás ahora,
                no se va a ejecutar.
              </p>
            )}
            {counts.active > 0 && (
              <p className="alert alert-error" data-testid="close-active-warning" style={{ marginBottom: 12 }}>
                Hay {counts.active} {counts.active === 1 ? "sesión todavía en curso" : "sesiones todavía en curso"}: si
                cerrás ahora, quedarán sin análisis del modelo.
              </p>
            )}
          </ConfirmDialog>

          <ConfirmDialog
            open={confirmDeleteExam}
            title="¿Eliminar la evaluación?"
            tone="danger"
            confirmLabel={deletingExam ? "Eliminando…" : "Confirmar la eliminación"}
            busy={deletingExam}
            onConfirm={deleteExam}
            onCancel={() => setConfirmDeleteExam(false)}
          >
            <p>
              Se van a eliminar «{exam.name}» y sus {counts.total} sesiones, con todos sus datos. No se puede deshacer.
            </p>
          </ConfirmDialog>
        </>
      )}
    </div>
  );
}
