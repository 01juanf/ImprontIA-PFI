import { Link } from "react-router-dom";
import { usePageTitle } from "../a11y";
import { Wordmark } from "../ui";
import CodeEntry from "../CodeEntry";

/**
 * Ingreso del estudiante con solo el código del examen (evaluación de usabilidad, problema 2).
 * Pública: navega a la ruta del examen existente (/exam/:joinCode), que valida el código.
 */
export default function JoinExam() {
  usePageTitle("Ingresar a un examen");

  return (
    <div className="student on-black glow">
      <header className="student-bar">
        <Wordmark to="/" />
      </header>
      <main className="student-main enter">
        <span className="eyebrow">Paso 1 de 3</span>
        <h1>Ingresar a un examen</h1>
        <p className="lead" style={{ marginBottom: 28 }}>
          Escribí el código que te compartió tu docente. En el paso siguiente vas a ver qué se registra durante el
          examen, antes de aceptar.
        </p>
        <CodeEntry autoFocus />
        <p className="muted small" style={{ marginTop: 28 }}>
          ¿Sos docente? <Link to="/login">Ingresá al panel</Link>
        </p>
      </main>
    </div>
  );
}
