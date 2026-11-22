import { useRef, useState } from "react";
import { ExternalLink, FileText, Loader2, Upload } from "lucide-react";
import { api, type Exam } from "./api";

/** Abre el PDF del enunciado (descargado con el token docente) en una pestaña nueva. */
export async function openExamPdf(examId: string): Promise<boolean> {
  const win = window.open("", "_blank"); // se abre ya, dentro del clic, para que no lo bloquee el navegador
  try {
    const blob = await api.getExamPdf(examId);
    const url = URL.createObjectURL(new Blob([blob], { type: "application/pdf" }));
    if (win) win.location.href = url;
    else window.location.href = url;
    return true;
  } catch {
    win?.close();
    return false;
  }
}

/** Enunciado de la evaluación en Configuración: ejercicios escritos o PDF (con reemplazo). */
export default function EnunciadoCard({ exam, onUpdated }: { exam: Exam; onUpdated: () => void }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const input = useRef<HTMLInputElement | null>(null);
  const items = exam.items ?? null;

  async function replace(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setMsg(null);
    try {
      await api.uploadExamPdf(exam.id, file);
      setMsg({ ok: true, text: "PDF actualizado. Lo ven los estudiantes que ingresen a partir de ahora." });
      onUpdated();
    } catch {
      setMsg({ ok: false, text: "No se pudo subir el PDF (tiene que ser un PDF de hasta 4 MB)." });
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <section className="card" aria-labelledby={`enunciado-${exam.id}`}>
      <div className="card-head">
        <div>
          <h3 id={`enunciado-${exam.id}`}>Enunciado</h3>
          <p className="panel-note" style={{ marginTop: 4 }}>
            {items
              ? `${items.length} ${items.length === 1 ? "ejercicio" : "ejercicios"}, cada uno con su campo de respuesta.`
              : "Una sola consigna."}
          </p>
        </div>
        {(exam.tiene_pdf || items) && (
          <div className="btn-row">
            {exam.tiene_pdf && (
              <button
                className="btn btn-ghost"
                onClick={async () => {
                  if (!(await openExamPdf(exam.id))) setMsg({ ok: false, text: "No se pudo abrir el PDF." });
                }}
              >
                <ExternalLink size={15} aria-hidden="true" />
                Ver PDF
              </button>
            )}
            <button className="btn btn-ghost" onClick={() => input.current?.click()} disabled={busy}>
              {busy ? <Loader2 size={15} className="spin" aria-hidden="true" /> : <Upload size={15} aria-hidden="true" />}
              {exam.tiene_pdf ? "Reemplazar PDF" : "Subir PDF"}
            </button>
            <input
              ref={input}
              type="file"
              accept="application/pdf,.pdf"
              hidden
              onChange={(e) => replace(e.target.files?.[0])}
            />
          </div>
        )}
      </div>
      {msg && <div className={`alert ${msg.ok ? "alert-success" : "alert-error"}`}>{msg.text}</div>}
      {exam.tiene_pdf && (
        <p className="muted small" style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12 }}>
          <FileText size={15} aria-hidden="true" /> {exam.pdf_nombre}
        </p>
      )}
      {items ? (
        items.some((it) => it.enunciado) ? (
          <ol style={{ margin: 0, paddingLeft: 20, display: "grid", gap: 8 }}>
            {items.map((it) => (
              <li key={it.id} style={{ whiteSpace: "pre-wrap" }}>
                {it.enunciado || <span className="muted">(en el PDF)</span>}
              </li>
            ))}
          </ol>
        ) : (
          <div className="item-chips" style={{ marginTop: 0 }}>
            {items.map((it) => (
              <span key={it.id}>Ejercicio {it.id}</span>
            ))}
          </div>
        )
      ) : (
        <p style={{ whiteSpace: "pre-wrap" }}>{exam.prompt_text}</p>
      )}
    </section>
  );
}
