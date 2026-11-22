import { useEffect, useState } from "react";
import { BarChart3, HelpCircle } from "lucide-react";
import { api, type Panorama } from "./api";
import {
  MODEL_INDICATOR_NOTE,
  PANORAMA_GUIDE,
  PANORAMA_METRIC_LABELS,
  barWidth,
  formatPanoramaValue,
  formatPercent,
  indicatorLabel,
} from "./format";
import { EmptySimple, SkeletonRows, indicatorIcon } from "./ui";

const METRIC_NAMES: Record<string, string> = {
  mean_dwell_time_ms: "Tiempo medio de pulsación",
  std_dwell_time_ms: "Variabilidad de la pulsación",
  mean_flight_time_ms: "Tiempo medio entre teclas",
  mean_mouse_speed_px_ms: "Velocidad media del mouse",
  std_mouse_speed_px_ms: "Variabilidad de la velocidad del mouse",
};

function Guide({ text }: { text: string }) {
  return (
    <p className="guide">
      <HelpCircle size={15} aria-hidden="true" />
      <span>{text.replace(/^¿[^?]*\?\s*/, "")}</span>
    </p>
  );
}

/**
 * Panorama de la evaluación (Incremento 12, R1): cómo transcurrió la evaluación en conjunto.
 * Solo muestra lo que ya calculó el pipeline (GET /exams/{id}/panorama). Barras en CSS.
 */
export default function PanoramaView({ examId, onSettled }: { examId: string; onSettled?: () => void }) {
  const [data, setData] = useState<Panorama | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    setData(null);
    setError(false);
    api
      .getPanorama(examId)
      .then(setData)
      .catch(() => setError(true))
      .finally(() => onSettled?.());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [examId]);

  if (error) return <div className="alert alert-error">No se pudo cargar el panorama de la evaluación.</div>;
  if (!data) return <SkeletonRows rows={3} height={110} />;
  if (data.n_sesiones === 0)
    return (
      <EmptySimple icon={BarChart3} title="Todavía no hay entregas finalizadas">
        El panorama se arma con las sesiones finalizadas de esta evaluación.
      </EmptySimple>
    );

  const maxInd = Math.max(...data.indicadores.map((i) => i.sesiones), 0);
  const maxTop = Math.max(...data.modelo.metricas_frecuentes.map((m) => m.sesiones), 0);

  return (
    <div className="panorama enter">
      <div className="panorama-kpis">
        <div className="kpi">
          <div className="v">{data.n_sesiones}</div>
          <div className="l">sesiones finalizadas</div>
        </div>
        <div className="kpi">
          <div className="v" style={{ color: data.sesiones_requieren_revision ? "var(--warn)" : undefined }}>
            {formatPercent(data.sesiones_requieren_revision / data.n_sesiones)}
          </div>
          <div className="l">requieren revisión ({data.sesiones_requieren_revision})</div>
        </div>
        <div className="kpi">
          <div className="v">{formatPercent(data.modelo.porcentaje)}</div>
          <div className="l">con proceso distinto al de la cohorte ({data.modelo.sesiones_marcadas})</div>
        </div>
      </div>

      {data.cobertura && (
        <p className="muted small" data-testid="panorama-cobertura" style={{ marginBottom: 16 }}>
          Cobertura del modelo:{" "}
          {data.cobertura.evaluacion_cerrada
            ? `${data.cobertura.sesiones_evaluadas} de ${data.n_sesiones} sesiones evaluadas` +
              (data.cobertura.sesiones_no_evaluadas > 0 ? `, ${data.cobertura.sesiones_no_evaluadas} sin evaluar` : "")
            : "pendiente: el análisis poblacional se hace al cerrar la evaluación"}
          . Las métricas resumen solo las sesiones con datos de cada señal.
        </p>
      )}

      <section className="card">
        <h3>¿Qué conductas se repiten?</h3>
        <Guide text={PANORAMA_GUIDE.indicadores} />
        {data.indicadores.length === 0 ? (
          <p className="muted">Ninguna sesión generó indicadores.</p>
        ) : (
          <ul className="bars">
            {data.indicadores.map((i) => {
              const Icon = indicatorIcon(i.kind);
              return (
                <li key={i.kind}>
                  <span className="bar-label" style={{ display: "flex", gap: 8 }}>
                    <Icon size={15} aria-hidden="true" style={{ flex: "none", marginTop: 2, color: "var(--muted)" }} />
                    <span>
                      {indicatorLabel(i.kind)}
                      {i.permitidas_por_reglas > 0 && <small>{i.permitidas_por_reglas} permitido por las reglas</small>}
                    </span>
                  </span>
                  <span className="bar-track" role="img" aria-label={`${i.sesiones} sesiones (${formatPercent(i.porcentaje)})`}>
                    <span className={`bar-fill ${i.kind === "atipico_modelo_poblacional" ? "" : i.kind === "captura_incompleta" ? "info" : "warn"}`} style={{ width: barWidth(i.sesiones, maxInd) }} />
                  </span>
                  <span className="bar-value">
                    {i.sesiones} · {formatPercent(i.porcentaje)}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="card">
        <h3>¿El tiempo y la forma de trabajo fueron los esperados?</h3>
        <Guide text={PANORAMA_GUIDE.metricas} />
        <div className="table-wrap" style={{ border: "none" }}>
          <table className="table table-compact">
            <thead>
              <tr>
                <th>Métrica</th>
                <th className="num">Mediana</th>
                <th className="num">Rango típico (p25–p75)</th>
                <th className="num">Sesiones</th>
              </tr>
            </thead>
            <tbody>
              {data.metricas.map((m) => (
                <tr key={m.metric}>
                  <td>{PANORAMA_METRIC_LABELS[m.metric] ?? m.metric}</td>
                  <td className="num">{formatPanoramaValue(m.metric, m.mediana)}</td>
                  <td className="num">
                    {m.n ? `${formatPanoramaValue(m.metric, m.p25)} – ${formatPanoramaValue(m.metric, m.p75)}` : "Sin datos"}
                  </td>
                  <td className="num">{m.n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <h3>¿Qué sesiones conviene mirar primero?</h3>
        <Guide text={PANORAMA_GUIDE.modelo} />
        <p className="muted small" style={{ marginBottom: 14 }}>
          {MODEL_INDICATOR_NOTE} Variables con mayor desviación que más se repiten entre las {data.modelo.sesiones_marcadas}{" "}
          sesiones marcadas por el modelo.
        </p>
        {data.modelo.metricas_frecuentes.length === 0 ? (
          <p className="muted">
            {data.cobertura && !data.cobertura.evaluacion_cerrada
              ? "Todavía no hay análisis: se calcula al cerrar la evaluación."
              : "El modelo no marcó sesiones (o la cohorte no alcanzó 20 sesiones)."}
          </p>
        ) : (
          <ul className="bars">
            {data.modelo.metricas_frecuentes.map((m) => (
              <li key={m.metric}>
                <span className="bar-label">{METRIC_NAMES[m.metric] ?? m.metric}</span>
                <span className="bar-track" role="img" aria-label={`${m.sesiones} sesiones marcadas`}>
                  <span className="bar-fill" style={{ width: barWidth(m.sesiones, maxTop) }} />
                </span>
                <span className="bar-value">{m.sesiones}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
