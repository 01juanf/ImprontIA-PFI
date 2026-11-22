import { useState, type FormEvent } from "react";
import { CheckCircle2, PenLine } from "lucide-react";
import { api, type Exam } from "./api";
import { RULE_OPTIONS, SIGNAL_OPTIONS, formatDateTime, signalLabel, type RuleFlag } from "./format";
import { SIGNAL_ICONS } from "./ui";

/**
 * Política de captura vigente de una evaluación y su edición (T11).
 *
 * Editar NO modifica la versión vigente: crea una versión nueva (POST
 * /exams/{id}/policy). Las sesiones ya iniciadas siguen ancladas a la versión
 * que el estudiante aceptó (RNF04); las nuevas sesiones toman la nueva.
 */
export default function PolicyCard({ exam, onUpdated }: { exam: Exam; onUpdated: () => void; collapsible?: boolean }) {
  const policy = exam.current_policy;
  const [editing, setEditing] = useState(false);
  const [infoText, setInfoText] = useState(policy.info_text);
  const [rulesText, setRulesText] = useState(policy.rules_text);
  const [signals, setSignals] = useState<string[]>(policy.allowed_signals);
  const [rules, setRules] = useState<Record<RuleFlag, boolean>>({
    permite_pegado: policy.permite_pegado,
    permite_otras_pestanas: policy.permite_otras_pestanas,
  });
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  function startEditing() {
    setInfoText(policy.info_text);
    setRulesText(policy.rules_text);
    setSignals(policy.allowed_signals);
    setRules({ permite_pegado: policy.permite_pegado, permite_otras_pestanas: policy.permite_otras_pestanas });
    setMsg(null);
    setEditing(true);
  }

  function toggleSignal(value: string) {
    setSignals((prev) => (prev.includes(value) ? prev.filter((s) => s !== value) : [...prev, value]));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    try {
      await api.updatePolicy(exam.id, { info_text: infoText, rules_text: rulesText, allowed_signals: signals, ...rules });
      setEditing(false);
      setMsg({
        ok: true,
        text: `Se creó la versión ${exam.policy_version + 1} de la política. Las sesiones ya iniciadas conservan la versión que aceptaron.`,
      });
      onUpdated();
    } catch {
      setMsg({ ok: false, text: "No se pudo guardar la nueva versión de la política." });
    }
  }

  return (
    <section className="card" aria-labelledby={`politica-titulo-${exam.id}`}>
      <div className="card-head">
        <div>
          <h3 id={`politica-titulo-${exam.id}`}>Política de captura · versión {exam.policy_version}</h3>
          <p className="panel-note" style={{ marginTop: 4 }}>
            Vigente desde {formatDateTime(policy.created_at)}. Es lo que ve el estudiante antes de consentir y define
            qué señales se registran.
          </p>
        </div>
        {!editing && (
          <button className="btn btn-ghost" onClick={startEditing}>
            <PenLine size={15} aria-hidden="true" />
            Editar (crea versión nueva)
          </button>
        )}
      </div>

      {msg && (
        <div className={`alert ${msg.ok ? "alert-success" : "alert-error"}`} role={msg.ok ? "status" : "alert"}>
          {msg.ok && <CheckCircle2 size={17} aria-hidden="true" />}
          <span className="alert-body">{msg.text}</span>
        </div>
      )}

      {!editing ? (
        <dl className="facts" id={`politica-${exam.id}`} style={{ gridTemplateColumns: "minmax(0,1fr)" }}>
          <div>
            <dt>Señales habilitadas</dt>
            <dd style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
              {policy.allowed_signals.length
                ? policy.allowed_signals.map((s) => {
                    const Icon = SIGNAL_ICONS[s];
                    return (
                      <span key={s} className="chip">
                        {Icon && <Icon size={13} aria-hidden="true" />} {signalLabel(s)}
                      </span>
                    );
                  })
                : "Ninguna"}
            </dd>
          </div>
          <div>
            <dt>Información previa</dt>
            <dd style={{ fontWeight: 400, whiteSpace: "pre-wrap" }}>{policy.info_text}</dd>
          </div>
          <div>
            <dt>Reglas</dt>
            <dd style={{ fontWeight: 400, whiteSpace: "pre-wrap" }}>{policy.rules_text}</dd>
          </div>
          <div>
            <dt>Permitido por las reglas</dt>
            <dd style={{ fontWeight: 400 }}>
              {RULE_OPTIONS.filter((o) => policy[o.value]).map((o) => o.label).join("; ") || "Nada adicional"}
            </dd>
          </div>
        </dl>
      ) : (
        <form onSubmit={handleSubmit}>
          <fieldset>
            <legend className="field-label" style={{ marginBottom: 10 }}>
              Señales habilitadas
            </legend>
            <div className="toggle-grid">
              {SIGNAL_OPTIONS.map((opt) => {
                const Icon = SIGNAL_ICONS[opt.value];
                return (
                  <label key={opt.value} className="toggle-card">
                    <Icon size={18} aria-hidden="true" />
                    <span>{opt.label}</span>
                    <input type="checkbox" checked={signals.includes(opt.value)} onChange={() => toggleSignal(opt.value)} />
                  </label>
                );
              })}
            </div>
          </fieldset>
          <label className="field">
            <span className="field-label">Información previa para el estudiante</span>
            <textarea value={infoText} onChange={(e) => setInfoText(e.target.value)} required />
          </label>
          <label className="field">
            <span className="field-label">Reglas y recursos permitidos</span>
            <textarea value={rulesText} onChange={(e) => setRulesText(e.target.value)} required />
          </label>
          <fieldset className="switch-list">
            <legend className="sr-only">Reglas del examen</legend>
            {RULE_OPTIONS.map((opt) => (
              <label key={opt.value} className="switch-row">
                <span>{opt.label}</span>
                <input
                  type="checkbox"
                  className="switch"
                  checked={rules[opt.value]}
                  onChange={(e) => setRules((prev) => ({ ...prev, [opt.value]: e.target.checked }))}
                />
              </label>
            ))}
          </fieldset>
          <p className="disclaimer" style={{ marginTop: 16 }}>
            Guardar crea la versión {exam.policy_version + 1}. No cambia lo que aceptaron los estudiantes que ya
            iniciaron su sesión.
          </p>
          <div className="btn-row">
            <button type="submit" className="btn btn-primary">
              Guardar como versión nueva
            </button>
            <button type="button" className="btn btn-quiet" onClick={() => setEditing(false)}>
              Cancelar
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
