import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronRight, ShieldCheck } from "lucide-react";
import { api, type SessionSummary } from "../api";
import { formatDateTime } from "../format";
import { usePageTitle } from "../a11y";
import { EmptySimple, SkeletonRows, Trace, shortWhen } from "../ui";

/**
 * RF11/HU08: casos en los que el docente indicó que la evidencia no alcanza y
 * pidió una validación adicional, de todas sus evaluaciones. ImprontIA no
 * ejecuta esa validación (cap. 13): solo deja constancia y la lista hasta que
 * una revisión posterior la cierre.
 */
export default function PendingValidations() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  usePageTitle("Validaciones pendientes");

  useEffect(() => {
    api
      .listSessions({ review_status: "validacion_pendiente" })
      .then(setSessions)
      .catch(() => setError("No se pudieron cargar las validaciones pendientes."))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Validaciones pendientes</h1>
          <p className="sub" style={{ maxWidth: "72ch" }}>
            Entregas en las que la evidencia no alcanzó. La validación (por ejemplo, una instancia oral) se hace fuera de
            ImprontIA; al terminarla, marcá la sesión como revisada para cerrar el pedido.
          </p>
        </div>
      </div>

      {error && (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <SkeletonRows rows={3} height={56} />
      ) : sessions.length === 0 ? (
        <EmptySimple icon={ShieldCheck} title="No hay validaciones pendientes">
          Cuando en una revisión marques «Requiere validación adicional», la sesión va a aparecer acá.
        </EmptySimple>
      ) : (
        <div className="table-wrap">
          <table className="table session-table">
            <thead>
              <tr>
                <th>Participante</th>
                <th>Evaluación</th>
                <th className="hide-sm">Indicadores</th>
                <th>Pedido</th>
                <th className="hide-sm">Nota del pedido</th>
                <th>
                  <span className="sr-only">Abrir</span>
                </th>
              </tr>
            </thead>
            <tbody className="stagger">
              {sessions.map((s, i) => (
                <tr key={s.id} style={{ ["--i" as string]: i }}>
                  <td className="nowrap">
                    <Link className="pid" to={`/sessions/${s.id}`} aria-label={`Ver detalle de ${s.participant_id}`}>
                      {s.participant_id}
                    </Link>
                  </td>
                  <td>{s.exam_name}</td>
                  <td className="hide-sm">
                    <Trace session={s} />
                  </td>
                  <td className="when" title={s.last_review_at ? formatDateTime(s.last_review_at) : undefined}>
                    {s.last_review_at ? shortWhen(s.last_review_at) : "Sin fecha"}
                  </td>
                  <td className="hide-sm muted small">{s.last_review_notes || "Sin nota"}</td>
                  <td className="go">
                    <ChevronRight size={18} aria-hidden="true" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
