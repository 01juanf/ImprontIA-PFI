import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, CheckCircle2, ChevronRight, ClipboardCheck, Plus, Share2, SquarePen, X } from "lucide-react";
import { api, apiErrorMessage, type Exam, type SessionSummary } from "../api";
import { usePageTitle } from "../a11y";
import CopyLinkButton from "../CopyLinkButton";
import { BrandMark, ExamStateChip, SkeletonRows, shortWhen } from "../ui";

interface ExamStats {
  total: number;
  flagged: number;
  reviewed: number;
}

export default function ExamsList() {
  const [exams, setExams] = useState<Exam[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  usePageTitle("Evaluaciones");
  // RF17: aviso que deja SessionsList al eliminar una evaluación; se muestra una vez.
  const location = useLocation();
  const navigate = useNavigate();
  const [flash, setFlash] = useState<string | null>((location.state as { msg?: string } | null)?.msg ?? null);
  useEffect(() => {
    if ((location.state as { msg?: string } | null)?.msg) navigate(location.pathname, { replace: true, state: null });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    Promise.all([api.listExams(), api.listSessions().catch(() => [] as SessionSummary[])])
      .then(([e, s]) => {
        // Primero las abiertas (son las que reciben entregas), después las más recientes.
        setExams(
          [...e].sort(
            (a, b) =>
              Number(Boolean(a.cerrada_at)) - Number(Boolean(b.cerrada_at)) ||
              Date.parse(b.created_at) - Date.parse(a.created_at),
          ),
        );
        setSessions(s);
      })
      .catch((err) => setError(apiErrorMessage(err, "No se pudieron cargar las evaluaciones.")))
      .finally(() => setLoading(false));
  }, []);

  // Un solo pedido de sesiones alcanza para mostrar el avance de cada evaluación.
  const stats = useMemo(() => {
    const m = new Map<string, ExamStats>();
    for (const s of sessions) {
      const st = m.get(s.exam_id) ?? { total: 0, flagged: 0, reviewed: 0 };
      st.total += 1;
      if (s.needs_review && s.review_status === "sin_revision") st.flagged += 1;
      if (s.review_status === "revisada") st.reviewed += 1;
      m.set(s.exam_id, st);
    }
    return m;
  }, [sessions]);

  const toReview = [...stats.values()].reduce((a, s) => a + s.flagged, 0);
  // La evaluación con más entregas pendientes: el atajo del encabezado lleva ahí, ya filtrada.
  const busiest = [...exams].sort((a, b) => (stats.get(b.id)?.flagged ?? 0) - (stats.get(a.id)?.flagged ?? 0))[0];

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Evaluaciones</h1>
          {!loading && exams.length > 0 && (
            <p className="sub">
              <span>
                {exams.length} {exams.length === 1 ? "evaluación" : "evaluaciones"}
              </span>
              {toReview > 0 && busiest && (
                <>
                  <span aria-hidden="true">·</span>
                  <Link className="sub-link" to={`/exams/${busiest.id}/sessions?revision=1`}>
                    {toReview} {toReview === 1 ? "entrega para revisar" : "entregas para revisar"}
                    <ArrowRight size={14} aria-hidden="true" />
                  </Link>
                </>
              )}
            </p>
          )}
        </div>
        <Link className="btn btn-primary" to="/exams/nueva">
          <Plus size={17} aria-hidden="true" />
          Nueva evaluación
        </Link>
      </div>

      {error && (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
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

      {loading ? (
        <SkeletonRows rows={4} height={72} />
      ) : exams.length === 0 ? (
        <div className="empty enter">
          <BrandMark size={96} stroke={1.2} className="art" />
          <div>
            <h2>Creá tu primera evaluación</h2>
            <p className="muted">
              Una evaluación es un examen con su consigna y su política de captura: qué se registra y qué está
              permitido. Te lleva un par de minutos.
            </p>
            <ol className="steps3">
              <li>
                <strong>
                  <SquarePen size={16} aria-hidden="true" /> Crear
                </strong>
                Consigna, señales a registrar y reglas.
              </li>
              <li>
                <strong>
                  <Share2 size={16} aria-hidden="true" /> Compartir
                </strong>
                Los estudiantes entran con un código de 6 caracteres.
              </li>
              <li>
                <strong>
                  <ClipboardCheck size={16} aria-hidden="true" /> Revisar
                </strong>
                Las entregas con indicadores aparecen primero.
              </li>
            </ol>
            <Link className="btn btn-primary" to="/exams/nueva">
              <Plus size={17} aria-hidden="true" />
              Nueva evaluación
            </Link>
          </div>
        </div>
      ) : (
        <ul className="exam-list stagger" aria-label="Tus evaluaciones">
          {exams.map((exam, i) => {
            const st = stats.get(exam.id) ?? { total: 0, flagged: 0, reviewed: 0 };
            const rest = Math.max(0, st.total - st.flagged - st.reviewed);
            return (
              <li key={exam.id} className="exam-row" style={{ ["--i" as string]: i }}>
                <div className="exam-main">
                  <Link className="row-link" to={`/exams/${exam.id}/sessions`}>
                    {exam.name}
                  </Link>
                  <div className="row-meta">Creada {shortWhen(exam.created_at)}</div>
                </div>
                <div className="share">
                  <span className="join-code" aria-label={`Código para estudiantes ${exam.join_code}`}>
                    {exam.join_code}
                  </span>
                  <CopyLinkButton joinCode={exam.join_code} examName={exam.name} compact />
                </div>
                <div className="status-cell">
                  <ExamStateChip closed={Boolean(exam.cerrada_at)} />
                </div>
                <div className="progress-cell">
                  <span>
                    {st.total} {st.total === 1 ? "entrega" : "entregas"}
                    {st.flagged > 0 && (
                      <>
                        {" · "}
                        <b>{st.flagged} para revisar</b>
                      </>
                    )}
                  </span>
                  {st.total > 0 && (
                    <span className="mini-bar" aria-hidden="true">
                      <span className="s-warn" style={{ flex: st.flagged }} />
                      <span className="s-ok" style={{ flex: st.reviewed }} />
                      <span className="s-rest" style={{ flex: rest }} />
                    </span>
                  )}
                </div>
                <ChevronRight size={18} className="chev" aria-hidden="true" />
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
